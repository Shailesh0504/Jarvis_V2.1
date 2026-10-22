# plugins/whatsapp/contacts.py
"""
Local Contact Book and Intelligent Recipient Resolution Engine for Jarvis WhatsApp Plugin.
Provides privacy-first local contact caching without cloud leaks.
"""

import json
import logging
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from .models import WhatsAppContact

logger = logging.getLogger("jarvis.plugins.whatsapp.contacts")

SEED_CONTACTS: List[Dict[str, Any]] = [
    {"name": "Mummy", "phone_number": "+919876543210", "relationship": "mother", "aliases": ["mom", "maa", "mataji"], "is_trusted": True},
    {"name": "Papa", "phone_number": "+919876543211", "relationship": "father", "aliases": ["dad", "pitaji"], "is_trusted": True},
    {"name": "Rahul Sharma", "phone_number": "+919876543212", "relationship": "friend", "aliases": ["rahul"], "is_trusted": False},
    {"name": "Priya", "phone_number": "+919876543213", "relationship": "colleague", "aliases": ["priya verma"], "is_trusted": False},
    {"name": "Boss", "phone_number": "+919876543214", "relationship": "manager", "aliases": ["sir", "manager"], "is_trusted": False},
]


class ContactBook:
    """Local SQLite contact store with fuzzy name & alias matching."""

    def __init__(self, db_path: str = "data/whatsapp_contacts.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    phone_number TEXT,
                    relationship TEXT,
                    aliases TEXT,
                    is_trusted INTEGER DEFAULT 0
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contact_name ON contacts(name COLLATE NOCASE);")

        # Seed default contacts if empty
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM contacts")
            if cur.fetchone()[0] == 0:
                for c in SEED_CONTACTS:
                    aliases_str = json.dumps([a.lower() for a in c.get("aliases", [])])
                    cur.execute("""
                        INSERT OR IGNORE INTO contacts (name, phone_number, relationship, aliases, is_trusted)
                        VALUES (?, ?, ?, ?, ?)
                    """, (c["name"], c["phone_number"], c.get("relationship"), aliases_str, 1 if c.get("is_trusted") else 0))
                conn.commit()

    def add_contact(self, contact: WhatsAppContact) -> bool:
        """Adds or updates a local contact."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            aliases_str = json.dumps([a.lower() for a in contact.aliases])
            cur.execute("""
                INSERT INTO contacts (name, phone_number, relationship, aliases, is_trusted)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    phone_number=excluded.phone_number,
                    relationship=excluded.relationship,
                    aliases=excluded.aliases,
                    is_trusted=excluded.is_trusted
            """, (contact.name, contact.phone_number, contact.relationship, aliases_str, 1 if contact.is_trusted else 0))
            conn.commit()
            return True

    def get_all_contacts(self) -> List[WhatsAppContact]:
        """Returns all contacts."""
        contacts = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM contacts ORDER BY name ASC")
            for row in cur.fetchall():
                contacts.append(self._row_to_contact(row))
        return contacts

    def resolve_contact(self, query: str) -> Tuple[Optional[WhatsAppContact], List[WhatsAppContact]]:
        """
        Intelligently resolves a recipient query:
        - If query is a phone number (e.g. "+91...", "987..."), returns an ad-hoc contact.
        - If exactly 1 match found -> returns (contact, [contact])
        - If multiple matches found (ambiguity) -> returns (None, [c1, c2, ...])
        - If no match found -> returns (None, [])
        """
        clean_q = query.strip().lower()
        if not clean_q:
            return None, []

        # 1. Direct Phone Number check
        clean_digits = re.sub(r'[\s\-\(\)\+]', '', clean_q)
        if clean_digits.isdigit() and len(clean_digits) >= 10:
            formatted_phone = f"+{clean_digits}" if not query.startswith("+") else query.strip()
            return WhatsAppContact(name=formatted_phone, phone_number=formatted_phone), []

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # 2. Search all candidates (exact name, prefix, substring, or alias)
            cur.execute("""
                SELECT * FROM contacts 
                WHERE LOWER(name) = ? 
                   OR LOWER(name) LIKE ? 
                   OR aliases LIKE ?
                   OR aliases LIKE ?
            """, (clean_q, f"{clean_q}%", f'%"{clean_q}"%', f'%"{clean_q}%"'))
            rows = cur.fetchall()
            candidates = [self._row_to_contact(r) for r in rows]

            # Deduplicate by name
            unique_candidates = {c.name: c for c in candidates}
            cand_list = list(unique_candidates.values())

            if len(cand_list) == 1:
                return cand_list[0], cand_list
            elif len(cand_list) > 1:
                # Check if there is an exact full name match (e.g. "Rahul Sharma")
                exact_name_matches = [c for c in cand_list if c.name.lower() == clean_q]
                if len(exact_name_matches) == 1:
                    return exact_name_matches[0], cand_list
                # Ambiguous! Return None with candidate list
                return None, cand_list

        # Not found in address book; create provisional contact by name
        return WhatsAppContact(name=query.strip().capitalize()), []

    def delete_contact(self, name_or_phone: str) -> bool:
        """Deletes a contact by name or phone number."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM contacts WHERE LOWER(name) = ? OR phone_number = ?", (name_or_phone.strip().lower(), name_or_phone.strip()))
            conn.commit()
            return cur.rowcount > 0

    def _row_to_contact(self, row: sqlite3.Row) -> WhatsAppContact:
        aliases = json.loads(row["aliases"]) if row["aliases"] else []
        return WhatsAppContact(
            name=row["name"],
            phone_number=row["phone_number"],
            relationship=row["relationship"],
            aliases=aliases,
            is_trusted=bool(row["is_trusted"])
        )
