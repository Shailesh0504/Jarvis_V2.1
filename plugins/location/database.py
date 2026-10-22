# plugins/location/database.py
"""
Local Offline Worldwide Geographic Dataset and Database for Jarvis V2.
"""

import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from .models import GeoLocation, PlaceType

logger = logging.getLogger("jarvis.plugins.location.db")

# Universal Global Seed Dataset
GLOBAL_GEOGRAPHIC_DATA: List[Dict[str, Any]] = [
    # 1. Countries
    {
        "name": "India", "place_type": "country", "country_name": "India", "continent": "Asia",
        "capital": "New Delhi", "latitude": 20.5937, "longitude": 78.9629, "timezone": "Asia/Kolkata (IST, UTC+5:30)",
        "aliases": ["bharat", "hindustan", "ind"], "description": "South Asian country with 28 states and 8 union territories.",
        "extra_info": {"states_count": 28, "ut_count": 8, "currency": "Indian Rupee (INR)", "official_languages": ["Hindi", "English"]}
    },
    {
        "name": "United States of America", "place_type": "country", "country_name": "United States of America", "continent": "North America",
        "capital": "Washington, D.C.", "latitude": 37.0902, "longitude": -95.7129, "timezone": "UTC-5 to UTC-10",
        "aliases": ["usa", "us", "america", "united states"], "description": "North American country composed of 50 states.",
        "extra_info": {"states_count": 50, "currency": "US Dollar (USD)"}
    },
    {
        "name": "United Kingdom", "place_type": "country", "country_name": "United Kingdom", "continent": "Europe",
        "capital": "London", "latitude": 55.3781, "longitude": -3.4360, "timezone": "Europe/London (GMT/BST, UTC+0/+1)",
        "aliases": ["uk", "britain", "great britain", "england"], "description": "Island nation in northwestern Europe comprising England, Scotland, Wales, and Northern Ireland.",
        "extra_info": {"currency": "Pound Sterling (GBP)", "countries_count": 4}
    },
    {
        "name": "Japan", "place_type": "country", "country_name": "Japan", "continent": "Asia",
        "capital": "Tokyo", "latitude": 36.2048, "longitude": 138.2529, "timezone": "Asia/Tokyo (JST, UTC+9:00)",
        "aliases": ["nippon", "nihon", "jpn"], "description": "Island country in East Asia located in the northwest Pacific Ocean.",
        "extra_info": {"prefectures_count": 47, "currency": "Japanese Yen (JPY)"}
    },
    {
        "name": "France", "place_type": "country", "country_name": "France", "continent": "Europe",
        "capital": "Paris", "latitude": 46.2276, "longitude": 2.2137, "timezone": "Europe/Paris (CET, UTC+1:00)",
        "aliases": ["french republic", "fr"], "description": "Western European nation known for art, science, and philosophy.",
        "extra_info": {"regions_count": 18, "currency": "Euro (EUR)"}
    },
    {
        "name": "Germany", "place_type": "country", "country_name": "Germany", "continent": "Europe",
        "capital": "Berlin", "latitude": 51.1657, "longitude": 10.4515, "timezone": "Europe/Berlin (CET, UTC+1:00)",
        "aliases": ["deutschland", "de"], "description": "Central European nation with 16 constituent states.",
        "extra_info": {"states_count": 16, "currency": "Euro (EUR)"}
    },
    {
        "name": "Australia", "place_type": "country", "country_name": "Australia", "continent": "Oceania",
        "capital": "Canberra", "latitude": -25.2744, "longitude": 133.7751, "timezone": "UTC+8 to UTC+10:30",
        "aliases": ["oz", "aussie", "aus"], "description": "Sovereign country comprising the mainland Australian continent and Tasmania.",
        "extra_info": {"states_count": 6, "territories_count": 2, "currency": "Australian Dollar (AUD)"}
    },
    {
        "name": "Canada", "place_type": "country", "country_name": "Canada", "continent": "North America",
        "capital": "Ottawa", "latitude": 56.1304, "longitude": -106.3468, "timezone": "UTC-3.5 to UTC-8",
        "aliases": ["ca"], "description": "Country in North America consisting of 10 provinces and 3 territories.",
        "extra_info": {"provinces_count": 10, "territories_count": 3, "currency": "Canadian Dollar (CAD)"}
    },
    {
        "name": "United Arab Emirates", "place_type": "country", "country_name": "United Arab Emirates", "continent": "Asia",
        "capital": "Abu Dhabi", "latitude": 23.4241, "longitude": 53.8478, "timezone": "Asia/Dubai (GST, UTC+4:00)",
        "aliases": ["uae", "emirates"], "description": "Federation of seven emirates on the Arabian Peninsula.",
        "extra_info": {"emirates_count": 7, "currency": "UAE Dirham (AED)"}
    },
    {
        "name": "China", "place_type": "country", "country_name": "China", "continent": "Asia",
        "capital": "Beijing", "latitude": 35.8617, "longitude": 104.1954, "timezone": "Asia/Shanghai (CST, UTC+8:00)",
        "aliases": ["prc", "peoples republic of china"], "description": "East Asian country and the world's third largest by area.",
        "extra_info": {"currency": "Renminbi / Yuan (CNY)"}
    },
    {
        "name": "Russia", "place_type": "country", "country_name": "Russia", "continent": "Europe / Asia",
        "capital": "Moscow", "latitude": 61.5240, "longitude": 105.3188, "timezone": "UTC+2 to UTC+12",
        "aliases": ["russian federation", "ru"], "description": "Transcontinental country spanning Eastern Europe and Northern Asia.",
        "extra_info": {"currency": "Russian Ruble (RUB)"}
    },
    {
        "name": "Nepal", "place_type": "country", "country_name": "Nepal", "continent": "Asia",
        "capital": "Kathmandu", "latitude": 28.3949, "longitude": 84.1240, "timezone": "Asia/Kathmandu (NPT, UTC+5:45)",
        "aliases": ["nep"], "description": "Landlocked Himalayan country in South Asia.",
        "extra_info": {"currency": "Nepalese Rupee (NPR)"}
    },
    {
        "name": "Sri Lanka", "place_type": "country", "country_name": "Sri Lanka", "continent": "Asia",
        "capital": "Sri Jayawardenepura Kotte", "latitude": 7.8731, "longitude": 80.7718, "timezone": "Asia/Colombo (SLST, UTC+5:30)",
        "aliases": ["ceylon", "lanka"], "description": "Island country in South Asia located in the Indian Ocean.",
        "extra_info": {"commercial_capital": "Colombo", "currency": "Sri Lankan Rupee (LKR)"}
    },

    # 2. Major Worldwide & Indian Cities
    {
        "name": "Mumbai", "place_type": "city", "state_name": "Maharashtra", "country_name": "India", "continent": "Asia",
        "latitude": 19.0760, "longitude": 72.8777, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["bombay", "bambai"], "description": "Financial capital of India and capital city of Maharashtra state located on the west coast."
    },
    {
        "name": "Delhi", "place_type": "city", "state_name": "National Capital Territory of Delhi", "country_name": "India", "continent": "Asia",
        "capital": "New Delhi", "latitude": 28.6139, "longitude": 77.2090, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["new delhi", "dilli", "nct delhi"], "description": "National capital territory of India."
    },
    {
        "name": "Bangalore", "place_type": "city", "state_name": "Karnataka", "country_name": "India", "continent": "Asia",
        "latitude": 12.9716, "longitude": 77.5946, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["bengaluru", "bangaluru", "silicon valley of india"], "description": "Capital of Karnataka and premier IT hub of India."
    },
    {
        "name": "Kolkata", "place_type": "city", "state_name": "West Bengal", "country_name": "India", "continent": "Asia",
        "latitude": 22.5726, "longitude": 88.3639, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["calcutta"], "description": "Capital of West Bengal and primary commercial center of East India."
    },
    {
        "name": "Chennai", "place_type": "city", "state_name": "Tamil Nadu", "country_name": "India", "continent": "Asia",
        "latitude": 13.0827, "longitude": 80.2707, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["madras"], "description": "Capital of Tamil Nadu and major cultural and economic hub of South India."
    },
    {
        "name": "Hyderabad", "place_type": "city", "state_name": "Telangana", "country_name": "India", "continent": "Asia",
        "latitude": 17.3850, "longitude": 78.4867, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["city of pearls"], "description": "Capital of Telangana and major tech center."
    },
    {
        "name": "Pune", "place_type": "city", "state_name": "Maharashtra", "country_name": "India", "continent": "Asia",
        "latitude": 18.5204, "longitude": 73.8567, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["poona"], "description": "Major cultural and IT/automotive city in Maharashtra located southeast of Mumbai."
    },
    {
        "name": "Goa", "place_type": "state", "country_name": "India", "continent": "Asia",
        "capital": "Panaji", "latitude": 15.2993, "longitude": 74.1240, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["goa state"], "description": "State located on the southwest coast of India along the Arabian Sea."
    },
    {
        "name": "Washington, D.C.", "place_type": "city", "country_name": "United States of America", "continent": "North America",
        "capital": "Washington, D.C.", "latitude": 38.9072, "longitude": -77.0369, "timezone": "America/New_York (EST/EDT)",
        "aliases": ["washington dc", "dc"], "description": "Capital city of the United States."
    },
    {
        "name": "Washington", "place_type": "state", "country_name": "United States of America", "continent": "North America",
        "capital": "Olympia", "latitude": 47.7511, "longitude": -120.7401, "timezone": "America/Los_Angeles (PST/PDT)",
        "aliases": ["washington state", "wa"], "description": "State in the Pacific Northwest region of the United States."
    },
    {
        "name": "Ahmedabad", "place_type": "city", "state_name": "Gujarat", "country_name": "India", "continent": "Asia",
        "latitude": 23.0225, "longitude": 72.5714, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["amdavad"], "description": "Largest city and commercial capital of Gujarat."
    },
    {
        "name": "Jaipur", "place_type": "city", "state_name": "Rajasthan", "country_name": "India", "continent": "Asia",
        "latitude": 26.9124, "longitude": 75.7873, "timezone": "Asia/Kolkata (IST)",
        "aliases": ["pink city"], "description": "Capital of Rajasthan known for historic palaces and forts."
    },
    {
        "name": "London", "place_type": "city", "state_name": "England", "country_name": "United Kingdom", "continent": "Europe",
        "latitude": 51.5074, "longitude": -0.1278, "timezone": "Europe/London (GMT/BST)",
        "aliases": ["londan"], "description": "Capital and largest city of the United Kingdom and England located on the River Thames."
    },
    {
        "name": "Paris", "place_type": "city", "state_name": "Île-de-France", "country_name": "France", "continent": "Europe",
        "latitude": 48.8566, "longitude": 2.3522, "timezone": "Europe/Paris (CET)",
        "aliases": ["city of light", "peris"], "description": "Capital and most populous city of France."
    },
    {
        "name": "Tokyo", "place_type": "city", "state_name": "Tokyo Prefecture", "country_name": "Japan", "continent": "Asia",
        "latitude": 35.6762, "longitude": 139.6503, "timezone": "Asia/Tokyo (JST)",
        "aliases": ["tokiyo", "edo"], "description": "Capital and largest metropolis of Japan."
    },
    {
        "name": "New York", "place_type": "city", "state_name": "New York", "country_name": "United States of America", "continent": "North America",
        "latitude": 40.7128, "longitude": -74.0060, "timezone": "America/New_York (EST/EDT)",
        "aliases": ["nyc", "new york city", "the big apple"], "description": "Most populous city in the United States and premier global financial center."
    },
    {
        "name": "Boston", "place_type": "city", "state_name": "Massachusetts", "country_name": "United States of America", "continent": "North America",
        "latitude": 42.3601, "longitude": -71.0589, "timezone": "America/New_York (EST/EDT)",
        "aliases": ["boston ma"], "description": "Capital and largest city of the Commonwealth of Massachusetts."
    },
    {
        "name": "Dubai", "place_type": "city", "state_name": "Emirate of Dubai", "country_name": "United Arab Emirates", "continent": "Asia",
        "latitude": 25.2048, "longitude": 55.2708, "timezone": "Asia/Dubai (GST)",
        "aliases": [], "description": "Most populous city in the UAE and major global luxury and aviation hub."
    },
    {
        "name": "Singapore", "place_type": "city", "country_name": "Singapore", "continent": "Asia",
        "latitude": 1.3521, "longitude": 103.8198, "timezone": "Asia/Singapore (SGT, UTC+8:00)",
        "aliases": ["lion city"], "description": "Island city-state in Southeast Asia."
    },
    {
        "name": "Sydney", "place_type": "city", "state_name": "New South Wales", "country_name": "Australia", "continent": "Oceania",
        "latitude": -33.8688, "longitude": 151.2093, "timezone": "Australia/Sydney (AEST/AEDT)",
        "aliases": [], "description": "Capital of New South Wales and largest city in Australia."
    },

    # 3. Famous Landmarks & Geographical Features
    {
        "name": "Mount Everest", "place_type": "mountain", "country_name": "Nepal / China", "continent": "Asia",
        "latitude": 27.9881, "longitude": 86.9250,
        "aliases": ["everest", "sagarmatha", "chomolungma"], "description": "Earth's highest mountain above sea level (8,848.86 m), located in the Himalayas on the Nepal-China border."
    },
    {
        "name": "Taj Mahal", "place_type": "landmark", "state_name": "Uttar Pradesh", "district_name": "Agra", "country_name": "India", "continent": "Asia",
        "latitude": 27.1751, "longitude": 78.0421,
        "aliases": ["taj", "taj mahal agra"], "description": "Ivory-white marble mausoleum on the south bank of the Yamuna river in Agra, India, commissioned by Shah Jahan."
    },
    {
        "name": "Eiffel Tower", "place_type": "landmark", "state_name": "Île-de-France", "country_name": "France", "continent": "Europe",
        "latitude": 48.8584, "longitude": 2.2945,
        "aliases": ["tour eiffel"], "description": "Wrought-iron lattice tower on the Champ de Mars in Paris, France."
    },
    {
        "name": "Statue of Liberty", "place_type": "landmark", "state_name": "New York", "country_name": "United States of America", "continent": "North America",
        "latitude": 40.6892, "longitude": -74.0445,
        "aliases": ["liberty statue"], "description": "Colossal neoclassical sculpture on Liberty Island in New York Harbor."
    },
    {
        "name": "Burj Khalifa", "place_type": "landmark", "state_name": "Dubai", "country_name": "United Arab Emirates", "continent": "Asia",
        "latitude": 25.1972, "longitude": 55.2744,
        "aliases": ["burj dubai"], "description": "Skyscraper in Dubai, United Arab Emirates, and the tallest artificial structure in the world (828 m)."
    }
]


class LocationDatabase:
    """SQLite-backed local geographic store with full-text alias querying."""

    def __init__(self, db_path: str = "data/geography.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    place_type TEXT NOT NULL,
                    country_name TEXT NOT NULL,
                    state_name TEXT,
                    district_name TEXT,
                    continent TEXT NOT NULL,
                    capital TEXT,
                    latitude REAL,
                    longitude REAL,
                    timezone TEXT,
                    aliases TEXT,
                    description TEXT,
                    extra_json TEXT,
                    UNIQUE(name, country_name, place_type)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_loc_name ON locations(name COLLATE NOCASE);")

        # Populate with seed data
        self._seed_data()

    def _seed_data(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            for loc in GLOBAL_GEOGRAPHIC_DATA:
                aliases_str = json.dumps([a.lower() for a in loc.get("aliases", [])])
                extra_str = json.dumps(loc.get("extra_info", {}))
                cur.execute("""
                    INSERT OR IGNORE INTO locations (
                        name, place_type, country_name, state_name, district_name,
                        continent, capital, latitude, longitude, timezone,
                        aliases, description, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    loc["name"], loc["place_type"], loc["country_name"],
                    loc.get("state_name"), loc.get("district_name"), loc["continent"],
                    loc.get("capital"), loc.get("latitude"), loc.get("longitude"),
                    loc.get("timezone"), aliases_str, loc.get("description"), extra_str
                ))
            conn.commit()

    def find_location(self, query: str) -> Optional[GeoLocation]:
        """Resolves location by name or alias."""
        clean_q = query.strip().lower()
        if not clean_q:
            return None

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # 1. Exact Name match (case-insensitive)
            cur.execute("SELECT * FROM locations WHERE LOWER(name) = ? LIMIT 1", (clean_q,))
            row = cur.fetchone()
            if row:
                return self._row_to_location(row)

            # 2. Alias match (JSON array search)
            cur.execute("SELECT * FROM locations WHERE aliases LIKE ?", (f'%"{clean_q}"%',))
            row = cur.fetchone()
            if row:
                return self._row_to_location(row)

            # 3. Substring match
            cur.execute("SELECT * FROM locations WHERE LOWER(name) LIKE ? LIMIT 1", (f"%{clean_q}%",))
            row = cur.fetchone()
            if row:
                return self._row_to_location(row)

        return None

    def search_locations(self, query: str, limit: int = 5) -> List[GeoLocation]:
        """Searches locations by partial match."""
        clean_q = query.strip().lower()
        results = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM locations 
                WHERE LOWER(name) LIKE ? OR aliases LIKE ?
                LIMIT ?
            """, (f"%{clean_q}%", f'%"{clean_q}"%', limit))
            for row in cur.fetchall():
                results.append(self._row_to_location(row))
        return results

    def _row_to_location(self, row: sqlite3.Row) -> GeoLocation:
        aliases = json.loads(row["aliases"]) if row["aliases"] else []
        extra = json.loads(row["extra_json"]) if row["extra_json"] else {}
        return GeoLocation(
            name=row["name"],
            place_type=PlaceType(row["place_type"]),
            country_name=row["country_name"],
            state_name=row["state_name"],
            district_name=row["district_name"],
            continent=row["continent"],
            capital=row["capital"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            timezone=row["timezone"],
            aliases=aliases,
            description=row["description"],
            extra_info=extra
        )

    def get_all_locations(self) -> List[GeoLocation]:
        """Returns all stored locations in the database."""
        results = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM locations")
            for row in cur.fetchall():
                results.append(self._row_to_location(row))
        return results

    def find_by_country(self, country_name: str) -> List[GeoLocation]:
        """Returns all locations associated with a country."""
        clean_c = country_name.strip().lower()
        results = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM locations WHERE LOWER(country_name) LIKE ? OR LOWER(name) LIKE ?", (f"%{clean_c}%", f"%{clean_c}%"))
            for row in cur.fetchall():
                results.append(self._row_to_location(row))
        return results

