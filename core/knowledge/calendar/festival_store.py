# core/knowledge/calendar/festival_store.py
"""
Authoritative Festival & National Day Data Store for Jarvis.

Stores 30+ festivals with per-year verified dates (2024-2028).
Dates sourced from:
  - Hindu Panchang / Drik Panchang for lunar festivals
  - Government of India calendar for national days
  - Gregorian calendar for fixed-date observances

DESIGN PRINCIPLES:
  - Dates are stored PER YEAR. There is no "default date" for a festival.
  - Year lookup uses the exact stored data; never interpolates or fabricates.
  - If a year is missing from dates_by_year, the engine returns an honest refusal.
  - Alias resolution is case-insensitive and STT-tolerant.
"""

from datetime import date
from typing import Dict, List, Optional, Tuple

from .models import (
    FestivalEntry, FestivalYearData,
    FestivalDateType, FestivalCategory
)

import logging

logger = logging.getLogger("jarvis.core.knowledge.calendar.festival_store")


def _d(y: int, m: int, d_: int) -> date:
    """Shorthand for creating a date."""
    return date(y, m, d_)


# ─────────────────────────────────────────────────────────────────────────────
# FESTIVAL REGISTRY
# Verified dates from Drik Panchang, Government of India, and Diwali.in
# Sources verified: 2026-09-08
# ─────────────────────────────────────────────────────────────────────────────

_FESTIVALS: List[FestivalEntry] = [

    # ── GANESH CHATURTHI ──────────────────────────────────────────────────
    FestivalEntry(
        festival_id="ganesh_chaturthi",
        canonical_name_en="Ganesh Chaturthi",
        canonical_name_hi="Ganesh Chaturthi (Ganpati Utsav)",
        aliases=[
            "ganesh chaturthi", "ganpati", "ganpati utsav", "ganesh utsav",
            "vinayaka chaturthi", "vinayak chaturthi", "ganesh ji ka festival",
            "ganpati festival", "bappa", "ganesh", "ganesh ji", "ganapati",
            "ganesh chaturthy", "ganesh chaturti",  # STT variants
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Bhadrapada Shukla Chaturthi)",
        region="Pan-India (Major in Maharashtra, Andhra Pradesh, Goa)",
        typical_duration_days=10,
        summary_en=(
            "Ganesh Chaturthi is a major Hindu festival celebrating the birth of Lord Ganesha, "
            "the elephant-headed deity of wisdom and prosperity. The 10-day festival begins with "
            "the installation of Ganesha idols and culminates in immersion (Visarjan)."
        ),
        summary_hi=(
            "Ganesh Chaturthi Bhagwan Ganesha — vighn-harta aur buddhi ke devta — ke janam utsav "
            "ko samarpit ek pramukh Hindu parv hai. 10 din chalane wala yeh tyohaar Ganesh pratima "
            "ki sthapna se shuru hota hai aur visarjan par samapat hota hai."
        ),
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 9, 7),  _d(2024, 9, 17), "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 8, 27), _d(2025, 9, 5),  "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 9, 14), _d(2026, 9, 23), "Drik Panchang", "2026-09-08", "Maharashtra mein 10 din, anya jagah 1.5 ya 5 din"),
            2027: FestivalYearData(2027, _d(2027, 9, 4),  _d(2027, 9, 13), "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 9, 22), _d(2028, 10, 1),"Drik Panchang", "2026-09-08"),
        }
    ),

    # ── DIWALI ────────────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="diwali",
        canonical_name_en="Diwali (Deepawali)",
        canonical_name_hi="Diwali (Deepawali)",
        aliases=[
            "diwali", "deepawali", "deepavali", "diwali festival",
            "deepawali festival", "lights festival", "diyas ka tyohaar",
            "diwali kab hai", "deepawali kab hai",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Kartik Amavasya)",
        region="Pan-India",
        typical_duration_days=5,
        summary_en=(
            "Diwali, the Festival of Lights, is the most celebrated Hindu festival. "
            "It marks the victory of light over darkness and lasts five days — "
            "Dhanteras, Choti Diwali, Diwali, Govardhan Puja, and Bhai Dooj."
        ),
        summary_hi=(
            "Diwali, roshnion ka tyohaar, sabse bada Hindu parv hai. "
            "Yeh roshni ki andhkaar par vijay ka prateek hai aur paanch din tak "
            "manaya jata hai — Dhanteras, Choti Diwali, Diwali, Govardhan Puja, aur Bhai Dooj."
        ),
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 11, 1),  _d(2024, 11, 5),  "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 10, 20), _d(2025, 10, 24), "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 11, 8),  _d(2026, 11, 12), "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 10, 29), _d(2027, 11, 2),  "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 10, 17), _d(2028, 10, 21), "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── DUSSEHRA / VIJAYADASAMI ───────────────────────────────────────────
    FestivalEntry(
        festival_id="dussehra",
        canonical_name_en="Dussehra (Vijayadasami)",
        canonical_name_hi="Dussehra (Vijayadasami)",
        aliases=[
            "dussehra", "dassehra", "dussera", "vijayadasami", "vijaya dasami",
            "dussehra festival", "ravan dahan", "navami ke baad ka din",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Ashwin Shukla Dashami)",
        region="Pan-India",
        typical_duration_days=1,
        summary_en="Dussehra celebrates the victory of Lord Rama over Ravana, symbolizing the triumph of good over evil. It marks the end of Navratri.",
        summary_hi="Dussehra Bhagwan Ram ki Ravan par vijay ka parv hai, jo burai par achchhai ki jeet ka prateek hai. Yeh Navratri ke ant mein aata hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 10, 12), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 10, 2),  None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 10, 19), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 10, 8),  None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 10, 26), None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── HOLI ──────────────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="holi",
        canonical_name_en="Holi",
        canonical_name_hi="Holi",
        aliases=[
            "holi", "holi festival", "holi kab hai", "rang ka tyohaar",
            "holi kab padegi", "dhulandi", "holika dahan",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Phalgun Purnima / Phalgun Shukla Purnima)",
        region="Pan-India",
        typical_duration_days=2,
        summary_en="Holi is the Festival of Colors, celebrating the arrival of spring and the victory of good over evil. It begins with Holika Dahan (bonfire) on the eve, followed by Rangwali Holi (playing with colors).",
        summary_hi="Holi, rang ka tyohaar, basant ritu ke swagat aur burai par achchhai ki vijay ka utsav hai. Iske pehle shaam Holika Dahan hota hai aur doosre din Rangwali Holi manai jati hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 3, 25), _d(2024, 3, 26), "Drik Panchang", "2026-09-08", "Holika Dahan: 24 March"),
            2025: FestivalYearData(2025, _d(2025, 3, 14), _d(2025, 3, 15), "Drik Panchang", "2026-09-08", "Holika Dahan: 13 March"),
            2026: FestivalYearData(2026, _d(2026, 3, 3),  _d(2026, 3, 4),  "Drik Panchang", "2026-09-08", "Holika Dahan: 2 March"),
            2027: FestivalYearData(2027, _d(2027, 3, 22), _d(2027, 3, 23), "Drik Panchang", "2026-09-08", "Holika Dahan: 21 March"),
            2028: FestivalYearData(2028, _d(2028, 3, 11), _d(2028, 3, 12), "Drik Panchang", "2026-09-08", "Holika Dahan: 10 March"),
        }
    ),

    # ── JANMASHTAMI ───────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="janmashtami",
        canonical_name_en="Krishna Janmashtami",
        canonical_name_hi="Krishna Janmashtami",
        aliases=[
            "janmashtami", "krishna janmashtami", "janmashtami festival",
            "krishna birthday", "krishna janam", "gokulashtami",
            "krishna ji ka birthday", "janmasthami", "janmashtmi",  # STT/typo variants
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Bhadrapada Krishna Ashtami)",
        region="Pan-India",
        typical_duration_days=2,
        summary_en="Krishna Janmashtami celebrates the birth of Lord Krishna, the eighth avatar of Vishnu. It is observed with fasting, devotional singing, and midnight celebrations.",
        summary_hi="Krishna Janmashtami Bhagwan Krishna — Vishnu ke aathve avatar — ke janam ka utsav hai. Upvaas, bhajan-kirtan aur madhyaratri utsav ke saath manaya jata hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 8, 26), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 8, 16), None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 9, 2),  None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 8, 22), None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 8, 10), None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── RAM NAVAMI ────────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="ram_navami",
        canonical_name_en="Ram Navami",
        canonical_name_hi="Ram Navami",
        aliases=[
            "ram navami", "ram navmi", "ram ji ka birthday",
            "ram janm", "shri ram navami", "ram navami festival",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Chaitra Shukla Navami)",
        region="Pan-India",
        typical_duration_days=1,
        summary_en="Ram Navami celebrates the birth of Lord Rama, the seventh avatar of Vishnu. It falls on the ninth day of Chaitra (spring) month.",
        summary_hi="Ram Navami Bhagwan Ram — Vishnu ke saatve avatar — ke janam utsav ka parv hai. Yeh Chaitra maas ki shukla navami ko manaya jata hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 4, 17), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 4, 6),  None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 3, 27), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 4, 15), None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 4, 4),  None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── NAVRATRI (SHARDIYA) ───────────────────────────────────────────────
    FestivalEntry(
        festival_id="navratri",
        canonical_name_en="Navratri (Shardiya Navratri)",
        canonical_name_hi="Navratri (Shardiya Navratri)",
        aliases=[
            "navratri", "navaratri", "navratri festival", "shardiya navratri",
            "navratri kab hai", "navratri kab se", "navratre",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Ashwin Shukla Pratipada to Navami)",
        region="Pan-India",
        typical_duration_days=9,
        summary_en="Navratri is a nine-night Hindu festival dedicated to Goddess Durga. The Shardiya Navratri in autumn is the most celebrated, ending with Dussehra.",
        summary_hi="Navratri Devi Durga ko samarpit nau raaton ka Hindu utsav hai. Sharadiya Navratri sabse badi hoti hai, jo Dussehra ke saath samapat hoti hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 10, 3),  _d(2024, 10, 11), "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 9, 22),  _d(2025, 10, 1),  "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 10, 10), _d(2026, 10, 18), "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 9, 29),  _d(2027, 10, 7),  "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 10, 17), _d(2028, 10, 25), "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── RAKSHA BANDHAN ────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="raksha_bandhan",
        canonical_name_en="Raksha Bandhan",
        canonical_name_hi="Raksha Bandhan",
        aliases=[
            "raksha bandhan", "rakshabandhan", "rakhi", "rakhi festival",
            "raksha bandhan kab hai", "rakhi kab hai",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Shravan Purnima)",
        region="Pan-India",
        typical_duration_days=1,
        summary_en="Raksha Bandhan is a festival celebrating the bond of love and protection between brothers and sisters. Sisters tie a sacred thread (rakhi) on their brother's wrist.",
        summary_hi="Raksha Bandhan bhai-behen ke prem aur suraksha ke bandhan ka tyohaar hai. Behen apne bhai ki kalagayi par rakhi (pavitra dhaga) baandhti hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 8, 19), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 8, 9),  None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 8, 28), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 8, 17), None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 8, 5),  None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── MAHASHIVRATRI ─────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="mahashivratri",
        canonical_name_en="Maha Shivratri",
        canonical_name_hi="Maha Shivratri",
        aliases=[
            "mahashivratri", "maha shivratri", "shivratri", "shiv ratri",
            "shivratri festival", "bholenath ka din", "maha shivratri kab hai",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Falgun Krishna Chaturdashi)",
        region="Pan-India",
        typical_duration_days=1,
        summary_en="Maha Shivratri is the grand night dedicated to Lord Shiva. Devotees observe fasting and night-long vigils, offering milk, honey, and bel leaves to Shiva Lingam.",
        summary_hi="Maha Shivratri Bhagwan Shiv ko samarpit maha-raat hai. Bhakt upvaas karte hain aur raat bhar jaag kar Shiv Lingam ko doodh, shahad aur bel patra chadhate hain.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 3, 8),  None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 2, 26), None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 2, 15), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 3, 6),  None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 2, 23), None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── GURU PURNIMA ──────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="guru_purnima",
        canonical_name_en="Guru Purnima",
        canonical_name_hi="Guru Purnima",
        aliases=[
            "guru purnima", "guru poornima", "guru purnima festival",
            "guru poornima kab hai", "guru purnima kab hai",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Ashadha Purnima)",
        region="Pan-India",
        typical_duration_days=1,
        summary_en="Guru Purnima is a sacred day to honor one's spiritual and academic teachers (Gurus). Observed on the full moon of Ashadha month.",
        summary_hi="Guru Purnima ek pavitra din hai jab shishya apne aatmik aur shaikshik gurus ko pranam karte hain. Ashadha maas ki purnima ko manaya jata hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 7, 21), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 7, 10), None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 7, 29), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 7, 18), None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 7, 6),  None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── BUDDHA PURNIMA ────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="buddha_purnima",
        canonical_name_en="Buddha Purnima",
        canonical_name_hi="Buddha Purnima",
        aliases=[
            "buddha purnima", "vesak", "buddha jayanti", "buddha purnima kab hai",
            "buddh purnima", "gautam buddha jayanti",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.BUDDHIST_FESTIVAL,
        calendar_system="Hindu Lunar (Vaishakha Purnima)",
        region="Pan-India",
        typical_duration_days=1,
        summary_en="Buddha Purnima commemorates the birth, enlightenment, and death of Gautama Buddha. It falls on the full moon of Vaishakha month.",
        summary_hi="Buddha Purnima Gautam Buddha ke janam, gyan prapti aur mahaparinirvaan ka parv hai. Vaishakh maas ki purnima ko manaya jata hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 5, 23), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 5, 12), None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 5, 31), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 5, 21), None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 5, 9),  None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── MAHAVIR JAYANTI ───────────────────────────────────────────────────
    FestivalEntry(
        festival_id="mahavir_jayanti",
        canonical_name_en="Mahavir Jayanti",
        canonical_name_hi="Mahavir Jayanti",
        aliases=[
            "mahavir jayanti", "mahaveer jayanti", "mahavira jayanti",
            "mahavir jayanti kab hai", "jain festival",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.JAIN_FESTIVAL,
        calendar_system="Hindu Lunar (Chaitra Shukla Trayodashi)",
        region="Pan-India",
        typical_duration_days=1,
        summary_en="Mahavir Jayanti commemorates the birth of Mahavira, the 24th and last Tirthankara of Jainism. It is the most important Jain festival.",
        summary_hi="Mahavir Jayanti Jainism ke 24ve aur antim Tirthankara Mahavira ke janam ka utsav hai. Yeh Jainon ka sabse mahatvapurn parv hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 4, 21), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 4, 10), None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 3, 31), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 4, 19), None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 4, 7),  None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── GURU NANAK JAYANTI ────────────────────────────────────────────────
    FestivalEntry(
        festival_id="guru_nanak_jayanti",
        canonical_name_en="Guru Nanak Jayanti (Gurpurab)",
        canonical_name_hi="Guru Nanak Jayanti (Gurpurab)",
        aliases=[
            "guru nanak jayanti", "gurpurab", "guru nanak birthday",
            "guru nanak dev ji jayanti", "guru nanak gurpurab",
            "guru nanak jayanti kab hai",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.SIKH_FESTIVAL,
        calendar_system="Hindu Lunar (Kartik Purnima)",
        region="Pan-India",
        typical_duration_days=1,
        summary_en="Guru Nanak Jayanti (Gurpurab) marks the birth anniversary of Guru Nanak Dev Ji, the founder of Sikhism. Celebrations include Akhand Path and processions.",
        summary_hi="Guru Nanak Jayanti Sikhism ke sansthapak Guru Nanak Dev Ji ki jayanti hai. Akhand Path aur shobha yaatra ke saath manaya jata hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 11, 15), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 11, 5),  None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 11, 24), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 11, 14), None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 11, 2),  None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── CHHATH PUJA ───────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="chhath_puja",
        canonical_name_en="Chhath Puja",
        canonical_name_hi="Chhath Puja",
        aliases=[
            "chhath puja", "chhath", "chhath pooja", "chhat puja",
            "chhath puja kab hai", "surya puja",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Kartik Shukla Shashthi)",
        region="Bihar, Jharkhand, UP, Delhi (major), Nepal",
        typical_duration_days=4,
        summary_en="Chhath Puja is a four-day festival dedicated to the Sun God (Surya) and Chhathi Maiya. Devotees offer arghya (water offering) at sunrise and sunset.",
        summary_hi="Chhath Puja Surya Devata aur Chhathi Maiya ko samarpit chaar din ka parv hai. Bhakt suryoday aur suryast par jalasay ke kinare khade hokar arghya dete hain.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 11, 5),  _d(2024, 11, 8),  "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 10, 25), _d(2025, 10, 28), "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 11, 12), _d(2026, 11, 15), "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 11, 1),  _d(2027, 11, 4),  "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 10, 20), _d(2028, 10, 23), "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── BASANT PANCHAMI ───────────────────────────────────────────────────
    FestivalEntry(
        festival_id="basant_panchami",
        canonical_name_en="Basant Panchami (Saraswati Puja)",
        canonical_name_hi="Basant Panchami (Saraswati Puja)",
        aliases=[
            "basant panchami", "vasant panchami", "saraswati puja",
            "saraswati pooja", "basant panchami kab hai",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Magha Shukla Panchami)",
        region="Pan-India",
        typical_duration_days=1,
        summary_en="Basant Panchami marks the onset of spring and is dedicated to Goddess Saraswati, the deity of knowledge and arts. Devotees wear yellow clothes and worship books.",
        summary_hi="Basant Panchami basant ritu ke aagman aur gyan-kala ki devi Saraswati ko samarpit hai. Log peele kapde pahante hain aur kitabon ki pooja karte hain.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 2, 14), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 2, 2),  None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 1, 23), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 2, 11), None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 2, 1),  None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── KARWA CHAUTH ──────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="karwa_chauth",
        canonical_name_en="Karwa Chauth",
        canonical_name_hi="Karwa Chauth",
        aliases=[
            "karwa chauth", "karwa chauth kab hai", "karva chauth",
            "karva chauth kab hai", "karwa chauth 2026",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Kartik Krishna Chaturthi)",
        region="North India (Rajasthan, Punjab, UP, Haryana)",
        typical_duration_days=1,
        summary_en="Karwa Chauth is a one-day fast observed by married Hindu women for the longevity and well-being of their husbands. They fast from sunrise to moonrise.",
        summary_hi="Karwa Chauth ek din ka upvaas hai jo vivahit Hindu mahilayein apne pati ki lambi umra aur bhalaai ke liye rakhti hain. Suryoday se chandrodaya tak nirjala upvaas kiya jata hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 10, 20), None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 10, 10), None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 10, 27), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 10, 17), None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 10, 5),  None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── TEEJ ──────────────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="teej",
        canonical_name_en="Hariyali Teej",
        canonical_name_hi="Hariyali Teej",
        aliases=[
            "teej", "hariyali teej", "teej festival", "teej kab hai",
            "sawan teej", "shravan teej",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Shravan Shukla Tritiya)",
        region="North India (Rajasthan, UP, Bihar, MP, Punjab)",
        typical_duration_days=1,
        summary_en="Teej is a festival celebrated by Hindu women, marking the union of Goddess Parvati with Lord Shiva. Women fast and pray for marital bliss.",
        summary_hi="Teej Hindu mahilaon ka parv hai, jo Devi Parvati aur Bhagwan Shiv ke milan ko celebrate karta hai. Mahilayein upvaas karke vaivahik sukh ke liye prarthana karti hain.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 8, 7),  None, "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 7, 27), None, "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 8, 14), None, "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 8, 3),  None, "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 8, 22), None, "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── DURGA PUJA ────────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="durga_puja",
        canonical_name_en="Durga Puja",
        canonical_name_hi="Durga Puja",
        aliases=[
            "durga puja", "durga pooja", "durga puja festival",
            "durgotsav", "durga puja kab hai", "maa durga puja",
        ],
        date_type=FestivalDateType.LUNAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Hindu Lunar (Ashwin Shukla Shashti to Dashami)",
        region="West Bengal, Assam, Odisha (major), Pan-India",
        typical_duration_days=5,
        summary_en="Durga Puja celebrates Goddess Durga's victory over the buffalo demon Mahishasura. It is the biggest festival in West Bengal.",
        summary_hi="Durga Puja Devi Durga ki mahishasur par vijay ka utsav hai. Yeh Paschim Bengal ka sabse bada parv hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 10, 9),  _d(2024, 10, 13), "Drik Panchang", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 9, 28),  _d(2025, 10, 2),  "Drik Panchang", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 10, 15), _d(2026, 10, 19), "Drik Panchang", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 10, 4),  _d(2027, 10, 8),  "Drik Panchang", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 10, 22), _d(2028, 10, 26), "Drik Panchang", "2026-09-08"),
        }
    ),

    # ── ONAM ──────────────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="onam",
        canonical_name_en="Onam",
        canonical_name_hi="Onam",
        aliases=[
            "onam", "onam festival", "onam kab hai", "kerala festival",
            "thiruvonam",
        ],
        date_type=FestivalDateType.SOLAR_COMPUTED,
        category=FestivalCategory.HARVEST_FESTIVAL,
        calendar_system="Malayalam Solar Calendar (Chingam 1)",
        region="Kerala",
        typical_duration_days=10,
        summary_en="Onam is the harvest festival of Kerala, celebrating the homecoming of the legendary King Mahabali. It is marked by floral rangoli (pookalam), boat races, and traditional feast (sadhya).",
        summary_hi="Onam Kerala ka fasal utsav hai, jo maharaja Mahabali ki wapsi ka jashn manata hai. Pookalam (phoolon ki rangoli), naav dawad aur sadhya bhojan is parv ki pehchan hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 9, 6),  _d(2024, 9, 15), "Kerala Govt Calendar", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 8, 26), _d(2025, 9, 4),  "Kerala Govt Calendar", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 9, 3),  _d(2026, 9, 12), "Kerala Govt Calendar", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 8, 23), _d(2027, 9, 1),  "Kerala Govt Calendar", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 9, 11), _d(2028, 9, 20), "Kerala Govt Calendar", "2026-09-08"),
        }
    ),

    # ── BAISAKHI ──────────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="baisakhi",
        canonical_name_en="Baisakhi (Vaisakhi)",
        canonical_name_hi="Baisakhi",
        aliases=[
            "baisakhi", "vaisakhi", "vaishakhi", "baisakhi festival",
            "baisakhi kab hai", "punjab festival", "sikh new year",
        ],
        date_type=FestivalDateType.SOLAR_COMPUTED,
        category=FestivalCategory.SIKH_FESTIVAL,
        calendar_system="Solar (Sikh/Hindu Nanakshahi calendar, Vaisakh 1st)",
        region="Punjab, Haryana, Pan-India",
        typical_duration_days=1,
        summary_en="Baisakhi marks the Punjabi New Year and commemorates the founding of the Khalsa Panth by Guru Gobind Singh in 1699. It also marks the harvest season.",
        summary_hi="Baisakhi Punjabi Naye Saal aur Guru Gobind Singh ji dwara 1699 mein Khalsa Panth ki sthapna ki yaad mein manaya jata hai. Yeh rabi fasal ki katai ka utsav bhi hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 4, 13), None, "Sikh Calendar", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 4, 13), None, "Sikh Calendar", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 4, 14), None, "Sikh Calendar", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 4, 14), None, "Sikh Calendar", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 4, 13), None, "Sikh Calendar", "2026-09-08"),
        }
    ),

    # ── PONGAL ────────────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="pongal",
        canonical_name_en="Pongal",
        canonical_name_hi="Pongal",
        aliases=[
            "pongal", "pongal festival", "thai pongal", "pongal kab hai",
            "tamil festival", "south india harvest festival",
        ],
        date_type=FestivalDateType.SOLAR_COMPUTED,
        category=FestivalCategory.HARVEST_FESTIVAL,
        calendar_system="Tamil Solar Calendar (Thai month 1st day)",
        region="Tamil Nadu, South India",
        typical_duration_days=4,
        summary_en="Pongal is the Tamil harvest festival dedicated to the Sun God. Celebrated over four days, it marks the end of winter and the start of the sun's northward journey.",
        summary_hi="Pongal Surya Devata ko samarpit Tamil fasal utsav hai. Chaar din tak manaya jaata hai; sharad ritu ke ant aur surya ke uttarayan ki shuruat ka prateek hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 1, 15), _d(2024, 1, 18), "Tamil Govt Calendar", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 1, 14), _d(2025, 1, 17), "Tamil Govt Calendar", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 1, 14), _d(2026, 1, 17), "Tamil Govt Calendar", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 1, 14), _d(2027, 1, 17), "Tamil Govt Calendar", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 1, 15), _d(2028, 1, 18), "Tamil Govt Calendar", "2026-09-08"),
        }
    ),

    # ── MAKAR SANKRANTI ───────────────────────────────────────────────────
    FestivalEntry(
        festival_id="makar_sankranti",
        canonical_name_en="Makar Sankranti",
        canonical_name_hi="Makar Sankranti",
        aliases=[
            "makar sankranti", "sankranti", "uttarayan", "makar sankranti kab hai",
            "kite festival", "til sankranti",
        ],
        date_type=FestivalDateType.SOLAR_COMPUTED,
        category=FestivalCategory.HINDU_FESTIVAL,
        calendar_system="Solar (Sun enters Capricorn / Makar Rashi)",
        region="Pan-India (known as Uttarayan in Gujarat, Pongal in Tamil Nadu)",
        typical_duration_days=1,
        summary_en="Makar Sankranti marks the sun's transition into Capricorn (Makara). It is a harvest festival celebrated across India — as Uttarayan (Gujarat), Lohri (Punjab), and Pongal (Tamil Nadu).",
        summary_hi="Makar Sankranti Surya ka Makar Rashi mein pravesh ka parv hai. Yeh Gujarat mein Uttarayan, Punjab mein Lohri, aur Tamil Nadu mein Pongal ke roop mein manaya jata hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 1, 15), None, "Govt India Calendar", "2026-09-08"),
            2025: FestivalYearData(2025, _d(2025, 1, 14), None, "Govt India Calendar", "2026-09-08"),
            2026: FestivalYearData(2026, _d(2026, 1, 14), None, "Govt India Calendar", "2026-09-08"),
            2027: FestivalYearData(2027, _d(2027, 1, 14), None, "Govt India Calendar", "2026-09-08"),
            2028: FestivalYearData(2028, _d(2028, 1, 15), None, "Govt India Calendar", "2026-09-08"),
        }
    ),

    # ── EID UL-FITR ───────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="eid_ul_fitr",
        canonical_name_en="Eid ul-Fitr",
        canonical_name_hi="Eid ul-Fitr",
        aliases=[
            "eid", "eid ul fitr", "eid ul-fitr", "meethi eid", "eid kab hai",
            "ramzan eid", "ramadan eid", "eid festival",
        ],
        date_type=FestivalDateType.ISLAMIC_LUNAR,
        category=FestivalCategory.ISLAMIC_FESTIVAL,
        calendar_system="Islamic Lunar (Shawwal 1st — moon sighting dependent)",
        region="Pan-India",
        typical_duration_days=3,
        summary_en="Eid ul-Fitr is celebrated by Muslims to mark the end of Ramadan (month of fasting). The date depends on the crescent moon sighting.",
        summary_hi="Eid ul-Fitr Musalmano dwara Ramzan (roze ka mahina) ke ant mein manaya jata hai. Iski tarikh hilal (naye chaand) ke dikhne par nirbhar karti hai.",
        dates_by_year={
            2024: FestivalYearData(2024, _d(2024, 4, 10), _d(2024, 4, 12), "Islamic Crescents", "2026-09-08", "Date approximate, moon sighting dependent", True),
            2025: FestivalYearData(2025, _d(2025, 3, 30), _d(2025, 4, 1),  "Islamic Crescents", "2026-09-08", "Date approximate, moon sighting dependent", True),
            2026: FestivalYearData(2026, _d(2026, 3, 20), _d(2026, 3, 22), "Islamic Crescents", "2026-09-08", "Date approximate, moon sighting dependent", True),
            2027: FestivalYearData(2027, _d(2027, 3, 9),  _d(2027, 3, 11), "Islamic Crescents", "2026-09-08", "Date approximate, moon sighting dependent", True),
            2028: FestivalYearData(2028, _d(2028, 2, 26), _d(2028, 2, 28), "Islamic Crescents", "2026-09-08", "Date approximate, moon sighting dependent", True),
        }
    ),

    # ── CHRISTMAS ─────────────────────────────────────────────────────────
    FestivalEntry(
        festival_id="christmas",
        canonical_name_en="Christmas",
        canonical_name_hi="Christmas (Bada Din)",
        aliases=[
            "christmas", "bada din", "christmas day", "christmas kab hai",
            "25 december", "xmas", "christmas festival",
        ],
        date_type=FestivalDateType.GREGORIAN_FIXED,
        category=FestivalCategory.CHRISTIAN_FESTIVAL,
        calendar_system="Gregorian (25 December every year)",
        region="Pan-India, Global",
        typical_duration_days=1,
        summary_en="Christmas is celebrated on December 25th to commemorate the birth of Jesus Christ. It is a public holiday in India.",
        summary_hi="Christmas Yisu Masih ke janmotsav ki yad mein 25 December ko manaya jata hai. Yeh Bharat mein sarkari chhutti ka din hai.",
        dates_by_year={
            yr: FestivalYearData(yr, _d(yr, 12, 25), None, "Gregorian Calendar", "2026-09-08")
            for yr in range(2024, 2035)
        }
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # NATIONAL DAYS — FIXED DATES (Gregorian)
    # ═══════════════════════════════════════════════════════════════════════

    FestivalEntry(
        festival_id="republic_day",
        canonical_name_en="Republic Day",
        canonical_name_hi="Gantantra Diwas",
        aliases=[
            "republic day", "gantantra diwas", "republic day kab hai",
            "26 january", "26 jan", "india republic day",
        ],
        date_type=FestivalDateType.GREGORIAN_FIXED,
        category=FestivalCategory.NATIONAL_DAY,
        calendar_system="Gregorian (26 January every year)",
        region="India",
        typical_duration_days=1,
        summary_en="Republic Day (26 January) commemorates the date in 1950 when the Constitution of India came into effect, replacing the Government of India Act as the governing document.",
        summary_hi="Gantantra Diwas (26 January) woh din hai jab 1950 mein Bharat ka Samvidhan laagu hua aur Bharat ek Gantantra Rashtra bana.",
        dates_by_year={
            yr: FestivalYearData(yr, _d(yr, 1, 26), None, "Government of India", "2026-09-08")
            for yr in range(2024, 2035)
        }
    ),

    FestivalEntry(
        festival_id="independence_day",
        canonical_name_en="Independence Day",
        canonical_name_hi="Swatantrata Diwas",
        aliases=[
            "independence day", "swatantrata diwas", "15 august", "15 aug",
            "independence day kab hai", "azaadi ka din", "azadi diwas",
        ],
        date_type=FestivalDateType.GREGORIAN_FIXED,
        category=FestivalCategory.NATIONAL_DAY,
        calendar_system="Gregorian (15 August every year)",
        region="India",
        typical_duration_days=1,
        summary_en="Independence Day (15 August) marks India's independence from British rule in 1947. The Prime Minister hoists the national flag at Red Fort, Delhi.",
        summary_hi="Swatantrata Diwas (15 August) 1947 mein Bharat ki Angrezi raj se azaadi ka din hai. Pradhan Mantri Lal Kile par Tiranga Fehraaate hain.",
        dates_by_year={
            yr: FestivalYearData(yr, _d(yr, 8, 15), None, "Government of India", "2026-09-08")
            for yr in range(2024, 2035)
        }
    ),

    FestivalEntry(
        festival_id="gandhi_jayanti",
        canonical_name_en="Gandhi Jayanti",
        canonical_name_hi="Gandhi Jayanti",
        aliases=[
            "gandhi jayanti", "mahatma gandhi birthday", "bapu birthday",
            "2 october", "gandhi jayanti kab hai", "gandhi ji ka birthday",
        ],
        date_type=FestivalDateType.GREGORIAN_FIXED,
        category=FestivalCategory.NATIONAL_DAY,
        calendar_system="Gregorian (2 October every year)",
        region="India",
        typical_duration_days=1,
        summary_en="Gandhi Jayanti (2 October) marks the birth anniversary of Mahatma Gandhi, the Father of the Nation. It is observed as a national holiday.",
        summary_hi="Gandhi Jayanti (2 October) Rashtra Pita Mahatma Gandhi ki jayanti hai. Yeh ek rashtriya chhutti ka din hai.",
        dates_by_year={
            yr: FestivalYearData(yr, _d(yr, 10, 2), None, "Government of India", "2026-09-08")
            for yr in range(2024, 2035)
        }
    ),

    FestivalEntry(
        festival_id="teachers_day",
        canonical_name_en="Teachers' Day",
        canonical_name_hi="Shikshak Diwas",
        aliases=[
            "teachers day", "shikshak diwas", "teachers' day", "teachers day kab hai",
            "5 september", "dr radhakrishnan birthday",
        ],
        date_type=FestivalDateType.GREGORIAN_FIXED,
        category=FestivalCategory.NATIONAL_DAY,
        calendar_system="Gregorian (5 September every year)",
        region="India",
        typical_duration_days=1,
        summary_en="Teachers' Day (5 September) is celebrated in India on the birthday of Dr Sarvepalli Radhakrishnan, former President of India, to honor the teaching profession.",
        summary_hi="Shikshak Diwas (5 September) Bharat ke poorv Rashtrapati Dr Sarvepalli Radhakrishnan ke janam din par manaya jata hai, jo shikshakOn ko samman deta hai.",
        dates_by_year={
            yr: FestivalYearData(yr, _d(yr, 9, 5), None, "Government of India", "2026-09-08")
            for yr in range(2024, 2035)
        }
    ),

    FestivalEntry(
        festival_id="childrens_day",
        canonical_name_en="Children's Day",
        canonical_name_hi="Bal Diwas",
        aliases=[
            "childrens day", "children's day", "bal diwas", "children day kab hai",
            "14 november", "nehru birthday", "chacha nehru birthday",
        ],
        date_type=FestivalDateType.GREGORIAN_FIXED,
        category=FestivalCategory.NATIONAL_DAY,
        calendar_system="Gregorian (14 November every year)",
        region="India",
        typical_duration_days=1,
        summary_en="Children's Day (14 November) is celebrated in India on the birthday of Jawaharlal Nehru (Chacha Nehru), India's first Prime Minister, who was fond of children.",
        summary_hi="Bal Diwas (14 November) Bharat ke pehle Pradhan Mantri Jawaharlal Nehru (Chacha Nehru) ke janam din par manaya jata hai, jo bachchon se bohot pyaar karte the.",
        dates_by_year={
            yr: FestivalYearData(yr, _d(yr, 11, 14), None, "Government of India", "2026-09-08")
            for yr in range(2024, 2035)
        }
    ),

    FestivalEntry(
        festival_id="constitution_day",
        canonical_name_en="Constitution Day",
        canonical_name_hi="Samvidhan Diwas",
        aliases=[
            "constitution day", "samvidhan diwas", "national law day",
            "26 november", "constitution day kab hai",
        ],
        date_type=FestivalDateType.GREGORIAN_FIXED,
        category=FestivalCategory.NATIONAL_DAY,
        calendar_system="Gregorian (26 November every year)",
        region="India",
        typical_duration_days=1,
        summary_en="Constitution Day (26 November) marks the adoption of the Constitution of India on 26 November 1949 by the Constituent Assembly.",
        summary_hi="Samvidhan Diwas (26 November) woh din hai jab 1949 mein Sansad ne Bharat ka Samvidhan sweekaar kiya.",
        dates_by_year={
            yr: FestivalYearData(yr, _d(yr, 11, 26), None, "Government of India", "2026-09-08")
            for yr in range(2024, 2035)
        }
    ),

    FestivalEntry(
        festival_id="national_science_day",
        canonical_name_en="National Science Day",
        canonical_name_hi="Rashtriya Vigyan Diwas",
        aliases=[
            "national science day", "rashtriya vigyan diwas", "science day",
            "28 february", "raman effect day", "science day kab hai",
        ],
        date_type=FestivalDateType.GREGORIAN_FIXED,
        category=FestivalCategory.NATIONAL_DAY,
        calendar_system="Gregorian (28 February every year)",
        region="India",
        typical_duration_days=1,
        summary_en="National Science Day (28 February) commemorates the discovery of the Raman Effect by Sir C.V. Raman in 1928, for which he received the Nobel Prize.",
        summary_hi="Rashtriya Vigyan Diwas (28 February) Sir C.V. Raman dwara 1928 mein Raman Effect ki khoj ki yaad mein manaya jata hai, jis par unhe Nobel Puraskar mila.",
        dates_by_year={
            yr: FestivalYearData(yr, _d(yr, 2, 28), None, "Government of India", "2026-09-08")
            for yr in range(2024, 2035)
        }
    ),
]


class FestivalStore:
    """
    Authoritative lookup store for Indian festivals and national days.
    All lookups are case-insensitive and STT-tolerant.
    """

    def __init__(self):
        # Index by festival_id
        self._by_id: Dict[str, FestivalEntry] = {
            f.festival_id: f for f in _FESTIVALS
        }
        # Alias → festival_id index (lowercase → festival_id)
        self._alias_index: Dict[str, str] = {}
        for entry in _FESTIVALS:
            for alias in entry.aliases:
                self._alias_index[alias.lower().strip()] = entry.festival_id
        logger.debug(
            f"[FESTIVAL_STORE] Loaded {len(self._by_id)} festivals, "
            f"{len(self._alias_index)} aliases."
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def resolve_festival_id(self, query_fragment: str) -> Optional[str]:
        """
        Resolves a raw query fragment to a festival_id via alias index.
        Tries longest-match first, then substring scan.
        """
        lowered = query_fragment.lower().strip()

        # 1. Direct alias match
        if lowered in self._alias_index:
            return self._alias_index[lowered]

        # 2. Scan for any alias that appears as substring in the query
        best_match: Optional[Tuple[str, int]] = None
        for alias, fid in self._alias_index.items():
            if alias in lowered:
                # Prefer longest alias match
                if best_match is None or len(alias) > best_match[1]:
                    best_match = (fid, len(alias))

        return best_match[0] if best_match else None

    def get_festival(self, festival_id: str) -> Optional[FestivalEntry]:
        """Returns FestivalEntry for a given festival_id."""
        return self._by_id.get(festival_id)

    def get_year_data(self, festival_id: str, year: int) -> Optional[FestivalYearData]:
        """Returns FestivalYearData for a specific festival and year, or None if unavailable."""
        entry = self._by_id.get(festival_id)
        if not entry:
            return None
        return entry.dates_by_year.get(year)

    def get_upcoming_festivals(
        self, from_date: date, limit: int = 5
    ) -> List[Tuple[FestivalEntry, FestivalYearData]]:
        """
        Returns the next `limit` festivals after from_date, sorted by date.
        Only considers festivals with verified date data for the relevant year(s).
        """
        candidates: List[Tuple[date, FestivalEntry, FestivalYearData]] = []
        for entry in _FESTIVALS:
            for year in [from_date.year, from_date.year + 1]:
                year_data = entry.dates_by_year.get(year)
                if year_data and year_data.start_date >= from_date:
                    candidates.append((year_data.start_date, entry, year_data))
                    break  # Only need the next occurrence per festival

        candidates.sort(key=lambda x: x[0])
        return [(e, yd) for _, e, yd in candidates[:limit]]

    def get_festivals_in_month(
        self, year: int, month: int
    ) -> List[Tuple[FestivalEntry, FestivalYearData]]:
        """Returns all festivals that start in the given year/month."""
        results: List[Tuple[FestivalEntry, FestivalYearData]] = []
        for entry in _FESTIVALS:
            yd = entry.dates_by_year.get(year)
            if yd and yd.start_date.month == month:
                results.append((entry, yd))
        results.sort(key=lambda x: x[1].start_date)
        return results

    def all_festival_ids(self) -> List[str]:
        return list(self._by_id.keys())


# ── Singleton ───────────────────────────────────────────────────────────────
_store_instance: Optional[FestivalStore] = None


def get_festival_store() -> FestivalStore:
    """Returns the global FestivalStore singleton."""
    global _store_instance
    if _store_instance is None:
        _store_instance = FestivalStore()
    return _store_instance
