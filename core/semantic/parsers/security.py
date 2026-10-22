# core/semantic/parsers/security.py
"""
Security, Credential, and Password Generation semantic parser.
Extracts structured entities: length, type, and options for password generation.
"""

import logging
import re
import secrets
import string
import subprocess
from typing import Optional, Tuple

from core.semantic.models import SemanticAction

logger = logging.getLogger("jarvis.security.parser")

PASSWORD_TRIGGER_RE = re.compile(
    r'\b(?:generate|banao|bana\s+do|bana\s+de|create|make|chahiye)\s+.*?\bpassword\b|\bpassword\b.*?\b(?:generate|banao|bana\s+do|bana\s+de|create|make)\b',
    re.IGNORECASE
)

PASSWORD_BARE_RE = re.compile(
    r'^(?:ek\s+)?password\s+(?:generate|banao|bana\s+do|chahiye)(?:\s+karo)?$',
    re.IGNORECASE
)

# Number extraction for password length (e.g., "8 digit password", "password of 12 characters")
LENGTH_PATTERNS = [
    re.compile(r'(\d+)\s*(?:digit|digits|char|chars|character|characters|ank|akshar)\b', re.IGNORECASE),
    re.compile(r'\b(?:length|size|of)\s*(\d+)\b', re.IGNORECASE),
    re.compile(r'(\d+)\s*(?:ka\s+)?password\b', re.IGNORECASE),
    re.compile(r'\bpassword\s*(?:of\s+)?(\d+)\b', re.IGNORECASE),
]


def generate_secure_password(length: int = 12) -> str:
    """
    Generates a cryptographically secure random password with guaranteed
    mix of lowercase, uppercase, digits, and special characters.
    Also copies the password to clipboard.
    """
    length = max(6, min(128, int(length)))

    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*()-_=+[]{}|;:,.<>?"
    all_chars = lowercase + uppercase + digits + symbols

    # Guarantee at least one of each character category
    pwd_chars = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]

    # Fill the remaining length with random choices from all characters
    for _ in range(length - len(pwd_chars)):
        pwd_chars.append(secrets.choice(all_chars))

    # Shuffle the characters using Fisher-Yates with secrets.randbelow
    for i in range(len(pwd_chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        pwd_chars[i], pwd_chars[j] = pwd_chars[j], pwd_chars[i]

    password = "".join(pwd_chars)

    # Copy to clipboard
    _copy_to_clipboard(password)

    return password


def _copy_to_clipboard(text: str) -> bool:
    """Copies text to system clipboard via pyperclip or Windows PowerShell."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        pass

    try:
        # Fallback to Windows clip.exe or PowerShell
        process = subprocess.Popen(
            ["clip.exe"], stdin=subprocess.PIPE, close_fds=True
        )
        process.communicate(input=text.encode("utf-8"))
        return True
    except Exception as e:
        logger.debug("Failed copying password to clipboard: %s", e)
        return False


def parse_password_generation(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """
    Extracts entities for password generation:
      length: int (e.g. 8, 12, 16)
      type: "password"
    Supports Hindi, Hinglish, and English phrasings.
    """
    if "password" not in lowered and "passcode" not in lowered:
        return None

    # Exclude Wi-Fi password inquiry (handled by parse_network)
    if any(k in lowered for k in ("wifi", "wi-fi", "saved password", "show password", "copy wifi")):
        return None

    # Check for password generation trigger
    has_gen = bool(PASSWORD_TRIGGER_RE.search(lowered) or PASSWORD_BARE_RE.search(lowered))
    if not has_gen:
        return None

    # Extract length entity
    extracted_length: Optional[int] = None
    for pat in LENGTH_PATTERNS:
        m = pat.search(lowered)
        if m:
            try:
                val = int(m.group(1))
                if 4 <= val <= 128:
                    extracted_length = val
                    break
            except Exception:
                pass

    if extracted_length is not None:
        return SemanticAction(
            intent="GENERATE_PASSWORD",
            service="security",
            action="generate_password",
            query=raw_text,
            parameters={
                "length": extracted_length,
                "type": "password",
            },
            confidence=1.0,
        )

    # Length not specified -> Needs clarification (locks into workflow)
    return SemanticAction(
        intent="GENERATE_PASSWORD",
        service="security",
        action="generate_password",
        query=raw_text,
        parameters={"type": "password"},
        needs_clarification=True,
        missing_slot="length",
        clarification_prompt="Kitne characters ka?",
        confidence=0.95,
    )
