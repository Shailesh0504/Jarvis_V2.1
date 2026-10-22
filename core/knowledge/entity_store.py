# core/knowledge/entity_store.py
"""
Structured Semantic Entity & Fact Knowledge Store for Jarvis V2.1.
Stores canonical entities, properties, and relations across all 16 general knowledge categories.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
import logging
import re
from .models import KnowledgeEntity, KnowledgeRelation, KnowledgeCategory
from .data import ALL_EXPANDED_ENTITIES

logger = logging.getLogger("jarvis.core.knowledge.entity_store")


# Initial Seed Knowledge Graph
_SEED_ENTITIES: List[KnowledgeEntity] = [
    # -------------------------------------------------------------
    # 1. COUNTRIES, CAPITALS, CONTINENTS, CURRENCIES
    # -------------------------------------------------------------
    KnowledgeEntity(
        entity_id="india",
        canonical_name="India",
        entity_type="country",
        aliases=["india", "bharat", "hindustan", "hindostan"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES, KnowledgeCategory.INDIAN_GK],
        properties={
            "capital": "New Delhi",
            "currency": "Indian Rupee (INR)",
            "continent": "Asia",
            "states_count": "28 states and 8 union territories",
            "prime_minister": "Narendra Modi",
            "president": "Droupadi Murmu",
            "national_animal": "Royal Bengal Tiger",
            "national_bird": "Indian Peacock",
            "national_flower": "Lotus",
            "national_tree": "Banyan Tree",
            "national_fruit": "Mango",
            "national_anthem": "Jana Gana Mana (written by Rabindranath Tagore)",
            "national_song": "Vande Mataram (written by Bankim Chandra Chattopadhyay)",
            "father_of_nation": "Mahatma Gandhi",
            "official_languages": "Hindi and English",
            "independence_day": "15 August 1947",
            "republic_day": "26 January 1950",
            "longest_river": "Ganga (2,525 km)",
            "population": "lagbhag 1.4 billion (140 crore)",
            "first_prime_minister": "Pandit Jawaharlal Nehru",
            "first_president": "Dr. Rajendra Prasad"
        },
        summary_en="India is a sovereign country in South Asia with 28 states and 8 union territories, whose capital is New Delhi.",
        summary_hi="Bharat Dakshin Asia ka ek vishal desh hai jisme 28 rajya aur 8 kendrashasit pradesh hain, aur iski rajdhani New Delhi hai."
    ),
    KnowledgeEntity(
        entity_id="new_delhi",
        canonical_name="New Delhi",
        entity_type="city",
        aliases=["new delhi", "delhi", "dilli", "nayi dilli"],
        categories=[KnowledgeCategory.CAPITALS, KnowledgeCategory.CITIES, KnowledgeCategory.INDIAN_GK],
        properties={
            "capital_of": "India",
            "country": "India",
            "population": "Approximately 33 million (National Capital Region)",
            "language": "Hindi, English, Punjabi, Urdu",
            "famous_monuments": "India Gate, Red Fort, Qutub Minar"
        },
        summary_en="New Delhi is the capital of India and the seat of all three branches of the Government of India.",
        summary_hi="New Delhi Bharat ki rajdhani hai aur Bharat Sarkar ka mukhyalay hai."
    ),
    KnowledgeEntity(
        entity_id="usa",
        canonical_name="United States of America",
        entity_type="country",
        aliases=["usa", "united states", "america", "us", "u.s.a.", "u.s."],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES],
        properties={
            "capital": "Washington, D.C.",
            "currency": "US Dollar (USD)",
            "continent": "North America",
            "states_count": "50 states",
            "independence_day": "4 July 1776",
            "largest_city": "New York City"
        },
        summary_en="The United States of America is a North American country of 50 states, with its capital at Washington, D.C.",
        summary_hi="America 50 rajyon se bana ek desh hai, jiski rajdhani Washington, D.C. hai."
    ),
    KnowledgeEntity(
        entity_id="uk",
        canonical_name="United Kingdom",
        entity_type="country",
        aliases=["uk", "united kingdom", "britain", "great britain", "england"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES],
        properties={
            "capital": "London",
            "currency": "Pound Sterling (GBP)",
            "continent": "Europe"
        },
        summary_en="The United Kingdom is an island nation in northwestern Europe, with London as its capital.",
        summary_hi="United Kingdom Europe ka ek pramukh desh hai, jiski rajdhani London hai."
    ),
    KnowledgeEntity(
        entity_id="france",
        canonical_name="France",
        entity_type="country",
        aliases=["france", "franc"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES],
        properties={
            "capital": "Paris",
            "currency": "Euro (EUR)",
            "continent": "Europe",
            "famous_monument": "Eiffel Tower"
        },
        summary_en="France is a Western European nation whose capital is Paris.",
        summary_hi="France Western Europe ka desh hai, jiski rajdhani Paris hai."
    ),
    KnowledgeEntity(
        entity_id="germany",
        canonical_name="Germany",
        entity_type="country",
        aliases=["germany", "deutschland"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES],
        properties={
            "capital": "Berlin",
            "currency": "Euro (EUR)",
            "continent": "Europe"
        },
        summary_en="Germany is a central European country with Berlin as its capital.",
        summary_hi="Germany Europe ka ek desh hai, jiski rajdhani Berlin hai."
    ),
    KnowledgeEntity(
        entity_id="japan",
        canonical_name="Japan",
        entity_type="country",
        aliases=["japan", "nippon", "nihon"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES],
        properties={
            "capital": "Tokyo",
            "currency": "Japanese Yen (JPY)",
            "continent": "Asia"
        },
        summary_en="Japan is an island country in East Asia with Tokyo as its capital.",
        summary_hi="Japan East Asia ka ek dweep desh hai, jiski rajdhani Tokyo hai."
    ),
    KnowledgeEntity(
        entity_id="russia",
        canonical_name="Russia",
        entity_type="country",
        aliases=["russia", "roos"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES],
        properties={
            "capital": "Moscow",
            "currency": "Russian Ruble (RUB)",
            "continent": "Eurasia (Europe and Asia)",
            "largest": "World's largest country by area"
        },
        summary_en="Russia is the largest country in the world by land area, with Moscow as its capital.",
        summary_hi="Roos kshetraphal ke hisaab se duniya ka sabse bada desh hai, jiski rajdhani Moscow hai."
    ),
    KnowledgeEntity(
        entity_id="china",
        canonical_name="China",
        entity_type="country",
        aliases=["china", "cheen"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES],
        properties={
            "capital": "Beijing",
            "currency": "Chinese Yuan (CNY / Renminbi)",
            "continent": "Asia",
            "famous_monument": "Great Wall of China"
        },
        summary_en="China is an East Asian nation with Beijing as its capital.",
        summary_hi="China East Asia ka desh hai, jiski rajdhani Beijing hai."
    ),
    KnowledgeEntity(
        entity_id="australia",
        canonical_name="Australia",
        entity_type="country",
        aliases=["australia"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES, KnowledgeCategory.CONTINENTS],
        properties={
            "capital": "Canberra",
            "currency": "Australian Dollar (AUD)",
            "continent": "Australia / Oceania",
            "largest_city": "Sydney"
        },
        summary_en="Australia is both a country and a continent, with Canberra as its federal capital.",
        summary_hi="Australia ek desh aur mahadweep dono hai, aur iski rajdhani Canberra hai."
    ),
    KnowledgeEntity(
        entity_id="canada",
        canonical_name="Canada",
        entity_type="country",
        aliases=["canada"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES],
        properties={
            "capital": "Ottawa",
            "currency": "Canadian Dollar (CAD)",
            "continent": "North America"
        },
        summary_en="Canada is a North American country with Ottawa as its capital.",
        summary_hi="Canada North America ka desh hai, jiski rajdhani Ottawa hai."
    ),
    KnowledgeEntity(
        entity_id="brazil",
        canonical_name="Brazil",
        entity_type="country",
        aliases=["brazil", "brasil"],
        categories=[KnowledgeCategory.COUNTRIES, KnowledgeCategory.CAPITALS, KnowledgeCategory.CURRENCIES],
        properties={
            "capital": "Brasília",
            "currency": "Brazilian Real (BRL)",
            "continent": "South America"
        },
        summary_en="Brazil is the largest country in South America, with Brasília as its capital.",
        summary_hi="Brazil South America ka sabse bada desh hai, jiski rajdhani Brasília hai."
    ),

    # -------------------------------------------------------------
    # 2. INDIAN STATES & CAPITALS
    # -------------------------------------------------------------
    KnowledgeEntity(
        entity_id="maharashtra",
        canonical_name="Maharashtra",
        entity_type="state",
        aliases=["maharashtra", "maha"],
        categories=[KnowledgeCategory.STATES, KnowledgeCategory.CAPITALS, KnowledgeCategory.INDIAN_GK],
        properties={
            "capital": "Mumbai",
            "country": "India",
            "language": "Marathi",
            "largest_city": "Mumbai"
        },
        summary_en="Maharashtra is a state in western India, with Mumbai as its capital and financial hub.",
        summary_hi="Maharashtra Bharat ka ek pashchimi rajya hai, jiski rajdhani Mumbai hai."
    ),
    KnowledgeEntity(
        entity_id="karnataka",
        canonical_name="Karnataka",
        entity_type="state",
        aliases=["karnataka"],
        categories=[KnowledgeCategory.STATES, KnowledgeCategory.CAPITALS, KnowledgeCategory.INDIAN_GK],
        properties={
            "capital": "Bengaluru (Bangalore)",
            "country": "India",
            "language": "Kannada",
            "nickname": "Silicon Valley of India"
        },
        summary_en="Karnataka is a southwestern Indian state with Bengaluru as its capital.",
        summary_hi="Karnataka Bharat ka ek rajya hai, jiski rajdhani Bengaluru hai."
    ),
    KnowledgeEntity(
        entity_id="uttar_pradesh",
        canonical_name="Uttar Pradesh",
        entity_type="state",
        aliases=["uttar pradesh", "up", "u.p."],
        categories=[KnowledgeCategory.STATES, KnowledgeCategory.CAPITALS, KnowledgeCategory.INDIAN_GK],
        properties={
            "capital": "Lucknow",
            "country": "India",
            "language": "Hindi",
            "famous_monument": "Taj Mahal (Agra)"
        },
        summary_en="Uttar Pradesh is the most populous state in India, with Lucknow as its capital.",
        summary_hi="Uttar Pradesh Bharat ka sabse zyada jansankhya wala rajya hai, jiski rajdhani Lucknow hai."
    ),
    KnowledgeEntity(
        entity_id="tamil_nadu",
        canonical_name="Tamil Nadu",
        entity_type="state",
        aliases=["tamil nadu", "tamilnadu", "tn"],
        categories=[KnowledgeCategory.STATES, KnowledgeCategory.CAPITALS, KnowledgeCategory.INDIAN_GK],
        properties={
            "capital": "Chennai",
            "country": "India",
            "language": "Tamil"
        },
        summary_en="Tamil Nadu is a southern Indian state, with Chennai as its capital.",
        summary_hi="Tamil Nadu Bharat ka ek dakshini rajya hai, jiski rajdhani Chennai hai."
    ),
    KnowledgeEntity(
        entity_id="rajasthan",
        canonical_name="Rajasthan",
        entity_type="state",
        aliases=["rajasthan"],
        categories=[KnowledgeCategory.STATES, KnowledgeCategory.CAPITALS, KnowledgeCategory.INDIAN_GK],
        properties={
            "capital": "Jaipur (Pink City)",
            "country": "India",
            "largest": "Largest Indian state by land area",
            "language": "Hindi and Rajasthani"
        },
        summary_en="Rajasthan is India's largest state by area, with Jaipur as its capital.",
        summary_hi="Rajasthan kshetraphal ki drishti se Bharat ka sabse bada rajya hai, jiski rajdhani Jaipur hai."
    ),
    KnowledgeEntity(
        entity_id="gujarat",
        canonical_name="Gujarat",
        entity_type="state",
        aliases=["gujarat"],
        categories=[KnowledgeCategory.STATES, KnowledgeCategory.CAPITALS, KnowledgeCategory.INDIAN_GK],
        properties={
            "capital": "Gandhinagar",
            "country": "India",
            "language": "Gujarati",
            "famous_monument": "Statue of Unity"
        },
        summary_en="Gujarat is a western state in India with Gandhinagar as its capital.",
        summary_hi="Gujarat Bharat ka pashchimi rajya hai, jiski rajdhani Gandhinagar hai."
    ),
    KnowledgeEntity(
        entity_id="west_bengal",
        canonical_name="West Bengal",
        entity_type="state",
        aliases=["west bengal", "paschim banga", "bengal"],
        categories=[KnowledgeCategory.STATES, KnowledgeCategory.CAPITALS, KnowledgeCategory.INDIAN_GK],
        properties={
            "capital": "Kolkata",
            "country": "India",
            "language": "Bengali"
        },
        summary_en="West Bengal is an eastern Indian state with Kolkata as its capital.",
        summary_hi="West Bengal Bharat ka ek poorvi rajya hai, jiski rajdhani Kolkata hai."
    ),

    # -------------------------------------------------------------
    # 3. PLANETS & SOLAR SYSTEM
    # -------------------------------------------------------------
    KnowledgeEntity(
        entity_id="sun",
        canonical_name="The Sun",
        entity_type="star",
        aliases=["sun", "surya", "suraj"],
        categories=[KnowledgeCategory.PLANETS, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "type": "Yellow Dwarf Star",
            "age": "Approximately 4.6 billion years",
            "distance_from_earth": "About 149.6 million kilometers (1 AU)",
            "light_reach_time": "About 8 minutes and 20 seconds",
            "primary_composition": "Hydrogen (73%) and Helium (25%)"
        },
        summary_en="The Sun is the star at the center of the Solar System.",
        summary_hi="Suraj hamare Solar System ke kendra mein sthit ek tara hai."
    ),
    KnowledgeEntity(
        entity_id="earth",
        canonical_name="Earth",
        entity_type="planet",
        aliases=["earth", "prithvi", "dharti"],
        categories=[KnowledgeCategory.PLANETS, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "position": "Third planet from the Sun",
            "moons_count": "1 natural satellite (The Moon)",
            "closest_planet": "Venus",
            "atmosphere": "78% Nitrogen, 21% Oxygen, 1% Other gases",
            "rotation_period": "24 hours",
            "orbit_period": "365.25 days (365 days and 6 hours)",
            "revolution_period": "365 days and 6 hours (365.25 days)",
            "diameter_km": 12742,
            "diameter": "12,742 km"
        },
        summary_en="Earth is the third planet from the Sun and the only astronomical object known to harbor life.",
        summary_hi="Prithvi Surya se teesra grah hai aur brahmand mein jeevan rakhne wala ekmatra grah hai."
    ),
    KnowledgeEntity(
        entity_id="mars",
        canonical_name="Mars",
        entity_type="planet",
        aliases=["mars", "mangal", "mangal grah", "red planet"],
        categories=[KnowledgeCategory.PLANETS, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "position": "Fourth planet from the Sun",
            "nickname": "The Red Planet",
            "moons_count": "2 moons (Phobos and Deimos)",
            "color_reason": "Iron oxide (rust) on its surface",
            "diameter_km": 6779,
            "diameter": "6,779 km"
        },
        summary_en="Mars is the fourth planet from the Sun, known as the Red Planet.",
        summary_hi="Mangal Surya se chautha grah hai jise Lal Grah bhi kaha jata hai."
    ),
    KnowledgeEntity(
        entity_id="jupiter",
        canonical_name="Jupiter",
        entity_type="planet",
        aliases=["jupiter", "brihaspati", "guru"],
        categories=[KnowledgeCategory.PLANETS, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "position": "Fifth planet from the Sun",
            "largest": "Largest planet in the Solar System",
            "type": "Gas Giant",
            "great_red_spot": "A giant storm bigger than Earth",
            "diameter_km": 139820,
            "diameter": "139,820 km"
        },
        summary_en="Jupiter is the fifth planet from the Sun and the largest in the Solar System.",
        summary_hi="Brihaspati Solar System ka sabse bada grah hai."
    ),
    KnowledgeEntity(
        entity_id="venus",
        canonical_name="Venus",
        entity_type="planet",
        aliases=["venus", "shukra", "shukra grah"],
        categories=[KnowledgeCategory.PLANETS, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "position": "Second planet from the Sun",
            "hottest": "Hottest planet in the Solar System (due to greenhouse effect)",
            "nickname": "Morning Star and Evening Star"
        },
        summary_en="Venus is the second planet from the Sun and the hottest planet in the Solar System.",
        summary_hi="Shukra Solar System ka sabse garm grah hai aur ise bhor ka tara bhi kehte hain."
    ),

    # -------------------------------------------------------------
    # 4. ELEMENTS & SCIENCE BASICS
    # -------------------------------------------------------------
    KnowledgeEntity(
        entity_id="hydrogen",
        canonical_name="Hydrogen",
        entity_type="element",
        aliases=["hydrogen"],
        categories=[KnowledgeCategory.ELEMENTS, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "chemical_formula": "H",
            "atomic_number": 1,
            "atomic_mass": "1.008 u",
            "lightest": "Lightest and most abundant element in the universe"
        },
        summary_en="Hydrogen is the chemical element with the symbol H and atomic number 1.",
        summary_hi="Hydrogen parmanu kramank 1 wala sabse halka aur brahmand ka sabse prachur tatva hai."
    ),
    KnowledgeEntity(
        entity_id="oxygen",
        canonical_name="Oxygen",
        entity_type="element",
        aliases=["oxygen", "o2"],
        categories=[KnowledgeCategory.ELEMENTS, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "chemical_formula": "O",
            "atomic_number": 8,
            "atomic_mass": "15.999 u",
            "abundance": "Makes up approximately 21% of Earth's atmosphere"
        },
        summary_en="Oxygen is a chemical element with symbol O and atomic number 8, vital for respiration.",
        summary_hi="Oxygen parmanu kramank 8 wala tatva hai jo jeevan ke liye shwasan mein avashyak hai."
    ),
    KnowledgeEntity(
        entity_id="gold",
        canonical_name="Gold",
        entity_type="element",
        aliases=["gold", "sona", "swarna", "au"],
        categories=[KnowledgeCategory.ELEMENTS, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "chemical_formula": "Au",
            "symbol": "Au",
            "atomic_number": 79,
            "atomic_mass": "196.97 u"
        },
        summary_en="Gold is a chemical element with symbol Au (from Latin: aurum) and atomic number 79.",
        summary_hi="Gold (Sona) parmanu sankhya 79 aur symbol Au wala rasayanik tatva hai."
    ),
    KnowledgeEntity(
        entity_id="water",
        canonical_name="Water",
        entity_type="compound",
        aliases=["water", "paani", "pani", "jal"],
        categories=[KnowledgeCategory.SCIENCE_BASICS, KnowledgeCategory.ELEMENTS],
        properties={
            "chemical_formula": "H2O",
            "boiling_point": "100°C (212°F) at sea level",
            "freezing_point": "0°C (32°F)",
            "density_maximum": "4°C"
        },
        summary_en="Water is a chemical compound consisting of two hydrogen atoms bonded to one oxygen atom (H2O).",
        summary_hi="Paani do hydrogen aur ek oxygen atom se milkar banta hai jiska sutra H2O hai."
    ),
    KnowledgeEntity(
        entity_id="light",
        canonical_name="Speed of Light",
        entity_type="constant",
        aliases=["speed of light", "light speed", "roshni ki gati", "prakash ki chaal"],
        categories=[KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "speed": "Approximately 299,792 kilometers per second (about 3 × 10^8 m/s in vacuum)"
        },
        summary_en="The speed of light in vacuum is exactly 299,792,458 meters per second.",
        summary_hi="Vacuum mein roshni ki gati lagbhag 3 lakh kilometer prati second hoti hai."
    ),

    # -------------------------------------------------------------
    # 5. HISTORICAL FACTS & IMPORTANT DATES
    # -------------------------------------------------------------
    KnowledgeEntity(
        entity_id="indian_independence",
        canonical_name="Indian Independence",
        entity_type="historical_event",
        aliases=["indian independence", "aazadi", "independence of india", "swatantrata diwas"],
        categories=[KnowledgeCategory.HISTORY, KnowledgeCategory.IMPORTANT_DATES, KnowledgeCategory.INDIAN_GK],
        properties={
            "date": "15 August 1947",
            "first_prime_minister": "Jawaharlal Nehru",
            "speech": "Tryst with Destiny"
        },
        summary_en="India gained independence from British rule on 15 August 1947.",
        summary_hi="Bharat ko 15 August 1947 ko British shasan se aazadi mili thi."
    ),
    KnowledgeEntity(
        entity_id="republic_day_india",
        canonical_name="Republic Day of India",
        entity_type="historical_event",
        aliases=["republic day", "gantantra diwas"],
        categories=[KnowledgeCategory.HISTORY, KnowledgeCategory.IMPORTANT_DATES, KnowledgeCategory.INDIAN_GK],
        properties={
            "date": "26 January 1950",
            "constitution_enacted": "Constitution of India came into effect"
        },
        summary_en="The Constitution of India came into effect on 26 January 1950, celebrated as Republic Day.",
        summary_hi="26 January 1950 ko Bharat ka Samvidhan lagu hua tha, jise Gantantra Diwas ke roop mein manaya jata hai."
    ),
    KnowledgeEntity(
        entity_id="moon_landing",
        canonical_name="Apollo 11 Moon Landing",
        entity_type="historical_event",
        aliases=["moon landing", "first man on moon", "chand par pehla kadam"],
        categories=[KnowledgeCategory.HISTORY, KnowledgeCategory.IMPORTANT_DATES, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "date": "20 July 1969",
            "first_person": "Neil Armstrong",
            "mission": "Apollo 11 (NASA)",
            "famous_quote": "'That's one small step for man, one giant leap for mankind.'"
        },
        summary_en="Neil Armstrong became the first human to walk on the Moon on 20 July 1969.",
        summary_hi="20 July 1969 ko Neil Armstrong Chandrama par kadam rakhne wale pehle insaan bane the."
    ),

    # -------------------------------------------------------------
    # 6. FAMOUS PEOPLE & INVENTIONS
    # -------------------------------------------------------------
    KnowledgeEntity(
        entity_id="isaac_newton",
        canonical_name="Sir Isaac Newton",
        entity_type="person",
        aliases=["isaac newton", "newton", "sir isaac newton"],
        categories=[KnowledgeCategory.FAMOUS_PEOPLE, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "known_for": "Laws of Motion and Universal Gravitation",
            "famous_work": "Philosophiae Naturalis Principia Mathematica (1687)",
            "inventor_of": "Reflecting telescope and Calculus (with Leibniz)"
        },
        summary_en="Sir Isaac Newton formulated the laws of motion and universal gravitation.",
        summary_hi="Sir Isaac Newton ne gurutwakarshan (gravity) aur gati ke teen niyamon ki khoj ki thi."
    ),
    KnowledgeEntity(
        entity_id="albert_einstein",
        canonical_name="Albert Einstein",
        entity_type="person",
        aliases=["albert einstein", "einstein"],
        categories=[KnowledgeCategory.FAMOUS_PEOPLE, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "known_for": "Theory of Relativity (E=mc²)",
            "famous_theory": "Theory of Relativity (E=mc²)",
            "theory": "Theory of Relativity",
            "nobel_prize": "1921 Nobel Prize in Physics for Photoelectric Effect"
        },
        summary_en="Albert Einstein developed the theory of relativity and is best known for E=mc².",
        summary_hi="Albert Einstein ne Relativity ki theory di aur unka prasiddh formula E=mc² hai."
    ),
    KnowledgeEntity(
        entity_id="thomas_edison",
        canonical_name="Thomas Edison",
        entity_type="person",
        aliases=["thomas edison", "edison"],
        categories=[KnowledgeCategory.FAMOUS_PEOPLE, KnowledgeCategory.SCIENCE_BASICS],
        properties={
            "inventor": "Practical incandescent light bulb, phonograph, and motion picture camera"
        },
        summary_en="Thomas Edison was an American inventor who developed the practical electric light bulb.",
        summary_hi="Thomas Edison ne practical electric bulb aur phonograph ka aavishkar kiya tha."
    ),
    KnowledgeEntity(
        entity_id="charles_babbage",
        canonical_name="Charles Babbage",
        entity_type="person",
        aliases=["charles babbage", "babbage", "father of computer"],
        categories=[KnowledgeCategory.FAMOUS_PEOPLE, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "known_for": "Father of the Computer",
            "inventor": "Mechanical computer designs: Difference Engine and Analytical Engine"
        },
        summary_en="Charles Babbage is considered the father of the computer for conceptualizing the Analytical Engine.",
        summary_hi="Charles Babbage ko Computer ka Pita (Father of Computer) mana jata hai."
    ),
    KnowledgeEntity(
        entity_id="computer",
        canonical_name="Computer",
        entity_type="technology",
        aliases=["computer", "computers", "sangnak"],
        categories=[KnowledgeCategory.COMPUTER_TECH, KnowledgeCategory.FAMOUS_PEOPLE],
        properties={
            "inventor": "Charles Babbage",
            "creator": "Charles Babbage",
            "father_of": "Charles Babbage"
        },
        summary_en="The computer was conceptualized by Charles Babbage, who designed the mechanical Analytical Engine.",
        summary_hi="Computer ka aavishkar Charles Babbage ne kiya tha jinhe Father of Computer kaha jata hai."
    ),
    KnowledgeEntity(
        entity_id="alexander_graham_bell",
        canonical_name="Alexander Graham Bell",
        entity_type="person",
        aliases=["alexander graham bell", "graham bell"],
        categories=[KnowledgeCategory.FAMOUS_PEOPLE],
        properties={
            "inventor": "Telephone (patented 1876)"
        },
        summary_en="Alexander Graham Bell is credited with patenting the first practical telephone.",
        summary_hi="Alexander Graham Bell ne telephone ka aavishkar kiya tha."
    ),
    KnowledgeEntity(
        entity_id="aryabhata",
        canonical_name="Aryabhata",
        entity_type="person",
        aliases=["aryabhata", "aryabhatt"],
        categories=[KnowledgeCategory.FAMOUS_PEOPLE, KnowledgeCategory.INDIAN_GK],
        properties={
            "known_for": "Introduction of zero (place-value system) and astronomical treatise Aryabhatiya",
            "era": "5th century CE (Ancient India)"
        },
        summary_en="Aryabhata was a great ancient Indian mathematician and astronomer who introduced the concept of zero.",
        summary_hi="Aryabhata prachin Bharat ke mahan ganitgya the jinhone shunya (zero) ki avadharna di thi."
    ),
    KnowledgeEntity(
        entity_id="apj_abdul_kalam",
        canonical_name="Dr. A.P.J. Abdul Kalam",
        entity_type="person",
        aliases=["abdul kalam", "dr kalam", "apj abdul kalam", "missile man"],
        categories=[KnowledgeCategory.FAMOUS_PEOPLE, KnowledgeCategory.INDIAN_GK],
        properties={
            "nickname": "Missile Man of India",
            "president": "11th President of India (2002-2007)",
            "known_for": "India's space and missile development programs (Agni and Prithvi missiles)"
        },
        summary_en="Dr. A.P.J. Abdul Kalam was India's 11th President and renowned scientist known as the Missile Man.",
        summary_hi="Dr. A.P.J. Abdul Kalam Bharat ke 11ve Rashtrapati aur mahan vaigyanik the jinhe Missile Man kaha jata hai."
    ),
    KnowledgeEntity(
        entity_id="mahatma_gandhi",
        canonical_name="Mahatma Gandhi",
        entity_type="person",
        aliases=["mahatma gandhi", "gandhi ji", "bapu", "father of nation", "father of the nation", "rashtrapita"],
        categories=[KnowledgeCategory.FAMOUS_PEOPLE, KnowledgeCategory.INDIAN_GK, KnowledgeCategory.HISTORY],
        properties={
            "full_name": "Mohandas Karamchand Gandhi",
            "birth_date": "2 October 1869 (Gandhi Jayanti / International Day of Non-Violence)",
            "father_of_nation": "Father of the Nation (India)",
            "known_for": "Ahimsa (Non-Violence) and Satyagraha"
        },
        summary_en="Mahatma Gandhi led India's non-violent independence movement and is revered as the Father of the Nation.",
        summary_hi="Mahatma Gandhi ne satya aur ahimsa ke marg par chalkar Bharat ko swatantrata dilayi thi."
    ),
    KnowledgeEntity(
        entity_id="dr_br_ambedkar",
        canonical_name="Dr. B.R. Ambedkar",
        entity_type="person",
        aliases=["dr br ambedkar", "bhimrao ambedkar", "babasaheb", "ambedkar"],
        categories=[KnowledgeCategory.FAMOUS_PEOPLE, KnowledgeCategory.INDIAN_GK, KnowledgeCategory.HISTORY],
        properties={
            "known_for": "Chief Architect of the Indian Constitution",
            "first_role": "India's first Law and Justice Minister",
            "birth_date": "14 April 1891 (Ambedkar Jayanti)"
        },
        summary_en="Dr. B.R. Ambedkar was a social reformer and the principal architect of the Constitution of India.",
        summary_hi="Dr. B.R. Ambedkar Bhartiya Samvidhan ke mukhya nirmata the."
    ),

    # -------------------------------------------------------------
    # 7. ABBREVIATIONS & TECH ACRONYMS
    # -------------------------------------------------------------
    KnowledgeEntity(
        entity_id="cpu",
        canonical_name="CPU",
        entity_type="acronym",
        aliases=["cpu", "c.p.u."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "full_form": "Central Processing Unit",
            "function": "The primary processor or 'brain' of a computer"
        },
        summary_en="CPU stands for Central Processing Unit, the primary component that executes computer instructions.",
        summary_hi="CPU ka full form Central Processing Unit hai, jise computer ka dimaag kaha jata hai."
    ),
    KnowledgeEntity(
        entity_id="ram",
        canonical_name="RAM",
        entity_type="acronym",
        aliases=["ram", "r.a.m."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "full_form": "Random Access Memory",
            "function": "Volatile high-speed working memory for active programs"
        },
        summary_en="RAM stands for Random Access Memory, temporary high-speed working memory.",
        summary_hi="RAM ka full form Random Access Memory hai, jo computer ki temporary working memory hoti hai."
    ),
    KnowledgeEntity(
        entity_id="rom",
        canonical_name="ROM",
        entity_type="acronym",
        aliases=["rom", "r.o.m."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "full_form": "Read Only Memory",
            "function": "Non-volatile permanent memory used for system boot firmware"
        },
        summary_en="ROM stands for Read Only Memory.",
        summary_hi="ROM ka full form Read Only Memory hai."
    ),
    KnowledgeEntity(
        entity_id="usb",
        canonical_name="USB",
        entity_type="acronym",
        aliases=["usb", "u.s.b."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "full_form": "Universal Serial Bus"
        },
        summary_en="USB stands for Universal Serial Bus.",
        summary_hi="USB ka full form Universal Serial Bus hai."
    ),
    KnowledgeEntity(
        entity_id="ai",
        canonical_name="AI",
        entity_type="acronym",
        aliases=["ai", "a.i."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "full_form": "Artificial Intelligence"
        },
        summary_en="AI stands for Artificial Intelligence.",
        summary_hi="AI ka full form Artificial Intelligence hai."
    ),
    KnowledgeEntity(
        entity_id="http",
        canonical_name="HTTP",
        entity_type="acronym",
        aliases=["http", "h.t.t.p."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "full_form": "Hypertext Transfer Protocol"
        },
        summary_en="HTTP stands for Hypertext Transfer Protocol.",
        summary_hi="HTTP ka full form Hypertext Transfer Protocol hai."
    ),
    KnowledgeEntity(
        entity_id="html",
        canonical_name="HTML",
        entity_type="acronym",
        aliases=["html", "h.t.m.l."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "full_form": "Hypertext Markup Language"
        },
        summary_en="HTML stands for Hypertext Markup Language.",
        summary_hi="HTML ka full form Hypertext Markup Language hai."
    ),
    KnowledgeEntity(
        entity_id="url",
        canonical_name="URL",
        entity_type="acronym",
        aliases=["url", "u.r.l."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "full_form": "Uniform Resource Locator"
        },
        summary_en="URL stands for Uniform Resource Locator.",
        summary_hi="URL ka full form Uniform Resource Locator hai."
    ),
    KnowledgeEntity(
        entity_id="isro",
        canonical_name="ISRO",
        entity_type="organization",
        aliases=["isro", "i.s.r.o."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.INDIAN_GK],
        properties={
            "full_form": "Indian Space Research Organisation",
            "headquarters": "Bengaluru, Karnataka",
            "founded": "15 August 1969 by Dr. Vikram Sarabhai"
        },
        summary_en="ISRO stands for Indian Space Research Organisation, India's premier space agency.",
        summary_hi="ISRO ka full form Indian Space Research Organisation hai, jiska mukhyalaya Bengaluru mein hai."
    ),
    KnowledgeEntity(
        entity_id="nasa",
        canonical_name="NASA",
        entity_type="organization",
        aliases=["nasa", "n.a.s.a."],
        categories=[KnowledgeCategory.ABBREVIATIONS],
        properties={
            "full_form": "National Aeronautics and Space Administration",
            "headquarters": "Washington, D.C., USA",
            "founded": "1958"
        },
        summary_en="NASA stands for National Aeronautics and Space Administration.",
        summary_hi="NASA ka full form National Aeronautics and Space Administration hai."
    ),
    KnowledgeEntity(
        entity_id="who",
        canonical_name="WHO",
        entity_type="organization",
        aliases=["who", "w.h.o."],
        categories=[KnowledgeCategory.ABBREVIATIONS],
        properties={
            "full_form": "World Health Organization",
            "headquarters": "Geneva, Switzerland"
        },
        summary_en="WHO stands for World Health Organization.",
        summary_hi="WHO ka full form World Health Organization hai."
    ),
    KnowledgeEntity(
        entity_id="upi",
        canonical_name="UPI",
        entity_type="acronym",
        aliases=["upi", "u.p.i."],
        categories=[KnowledgeCategory.ABBREVIATIONS, KnowledgeCategory.INDIAN_GK, KnowledgeCategory.COMPUTER_TECH],
        properties={
            "full_form": "Unified Payments Interface",
            "developed_by": "National Payments Corporation of India (NPCI)"
        },
        summary_en="UPI stands for Unified Payments Interface, India's instant real-time payment system.",
        summary_hi="UPI ka full form Unified Payments Interface hai."
    ),

    # -------------------------------------------------------------
    # 8. GEOGRAPHY SUPERLATIVES
    # -------------------------------------------------------------
    KnowledgeEntity(
        entity_id="mount_everest",
        canonical_name="Mount Everest",
        entity_type="landmark",
        aliases=["mount everest", "everest", "sagarmatha"],
        categories=[KnowledgeCategory.GEOGRAPHY],
        properties={
            "highest": "Highest mountain peak on Earth above sea level",
            "height": "8,848.86 meters (29,031.7 ft)",
            "location": "Himalayas, on the border between Nepal and China (Tibet)"
        },
        summary_en="Mount Everest is Earth's highest mountain above sea level at 8,848.86 meters.",
        summary_hi="Mount Everest duniya ki sabse unchi choti hai, jiski unchai 8,848.86 meter hai."
    ),
    KnowledgeEntity(
        entity_id="nile_river",
        canonical_name="Nile River",
        entity_type="river",
        aliases=["nile river", "nile", "neel nadi"],
        categories=[KnowledgeCategory.GEOGRAPHY],
        properties={
            "longest": "Longest river in the world",
            "length": "Approximately 6,650 kilometers (4,132 miles)",
            "continent": "Africa"
        },
        summary_en="The Nile River in northeastern Africa is generally considered the longest river on Earth.",
        summary_hi="Nile River duniya ki sabse lambi nadi hai jiski lambai lagbhag 6,650 km hai."
    ),
    KnowledgeEntity(
        entity_id="pacific_ocean",
        canonical_name="Pacific Ocean",
        entity_type="ocean",
        aliases=["pacific ocean", "prashant mahasagar", "pacific"],
        categories=[KnowledgeCategory.GEOGRAPHY],
        properties={
            "largest": "Largest and deepest ocean on Earth",
            "deepest_point": "Mariana Trench (Challenger Deep, ~11,034 meters)"
        },
        summary_en="The Pacific Ocean is the largest and deepest oceanic division on Earth.",
        summary_hi="Prashant Mahasagar (Pacific Ocean) duniya ka sabse bada aur sabse gehra mahasagar hai."
    ),
    KnowledgeEntity(
        entity_id="sahara_desert",
        canonical_name="Sahara Desert",
        entity_type="desert",
        aliases=["sahara desert", "sahara"],
        categories=[KnowledgeCategory.GEOGRAPHY],
        properties={
            "largest": "Largest hot desert in the world",
            "continent": "Africa"
        },
        summary_en="The Sahara is the largest hot desert in the world, covering much of North Africa.",
        summary_hi="Sahara duniya ka sabse bada garam registan hai jo North Africa mein sthit hai."
    ),

    # -------------------------------------------------------------
    # 9. COMPUTER & GENERAL TECHNOLOGY FACTS
    # -------------------------------------------------------------
    KnowledgeEntity(
        entity_id="python_programming",
        canonical_name="Python",
        entity_type="technology",
        aliases=["python", "python language"],
        categories=[KnowledgeCategory.COMPUTER_TECH],
        properties={
            "creator": "Guido van Rossum",
            "inventor": "Guido van Rossum",
            "year": "First released in 1991",
            "named_after": "Monty Python's Flying Circus"
        },
        summary_en="Python is a high-level programming language created by Guido van Rossum and released in 1991.",
        summary_hi="Python programming language ko Guido van Rossum ne 1991 mein banaya tha."
    ),
    KnowledgeEntity(
        entity_id="linux",
        canonical_name="Linux",
        entity_type="technology",
        aliases=["linux", "linux kernel"],
        categories=[KnowledgeCategory.COMPUTER_TECH],
        properties={
            "creator": "Linus Torvalds",
            "inventor": "Linus Torvalds",
            "year": "1991",
            "mascot": "Tux the Penguin"
        },
        summary_en="Linux is an open-source operating system kernel created by Linus Torvalds in 1991.",
        summary_hi="Linux open-source kernel ko Linus Torvalds ne 1991 mein develop kiya tha."
    ),
    KnowledgeEntity(
        entity_id="world_wide_web",
        canonical_name="World Wide Web",
        entity_type="technology",
        aliases=["www", "world wide web", "web"],
        categories=[KnowledgeCategory.COMPUTER_TECH, KnowledgeCategory.ABBREVIATIONS],
        properties={
            "inventor": "Tim Berners-Lee",
            "year": "Invented in 1989 at CERN"
        },
        summary_en="The World Wide Web was invented by English scientist Tim Berners-Lee in 1989.",
        summary_hi="World Wide Web (WWW) ka aavishkar Tim Berners-Lee ne 1989 mein CERN mein kiya tha."
    ),
    KnowledgeEntity(
        entity_id="windows",
        canonical_name="Microsoft Windows",
        entity_type="operating system",
        aliases=["windows", "ms windows", "microsoft windows", "windows os"],
        categories=[KnowledgeCategory.COMPUTER_TECH],
        properties={
            "creator": "Microsoft",
            "developer": "Microsoft",
            "latest_version": "Windows 11",
            "current_version": "Windows 11",
            "year": "First released in 1985"
        },
        summary_en="Microsoft Windows is an operating system family developed by Microsoft. The latest consumer release is Windows 11.",
        summary_hi="Microsoft Windows ek operating system family hai jise Microsoft ne develop kiya hai. Iska vartaman latest release Windows 11 hai."
    )
]


class EntityStore:
    """Indexed in-memory Semantic Entity and Knowledge Store."""

    def __init__(self):
        self.entities: Dict[str, KnowledgeEntity] = {}
        self.alias_map: Dict[str, str] = {}  # alias -> entity_id
        self.relations: List[KnowledgeRelation] = []
        self._load_seed_knowledge()

    def _load_seed_knowledge(self) -> None:
        """Loads and indexes the seed entities and expanded knowledge modules."""
        for entity in _SEED_ENTITIES:
            self.add_entity(entity)
        for entity in ALL_EXPANDED_ENTITIES:
            self.add_entity(entity)

    def add_entity(self, entity: KnowledgeEntity) -> None:
        """Registers an entity and indexes all its aliases, merging properties if entity already exists."""
        target_id = None
        if entity.entity_id in self.entities:
            target_id = entity.entity_id
        elif entity.canonical_name.lower() in self.alias_map:
            target_id = self.alias_map[entity.canonical_name.lower()]

        if target_id and target_id in self.entities:
            existing = self.entities[target_id]
            # Merge properties without overriding existing non-empty values
            for k, v in entity.properties.items():
                if k not in existing.properties or not existing.properties[k]:
                    existing.properties[k] = v
            # Merge categories
            for cat in entity.categories:
                if cat not in existing.categories:
                    existing.categories.append(cat)
            # Merge aliases
            for alias in entity.aliases:
                cleaned_a = alias.lower()
                if cleaned_a not in [a.lower() for a in existing.aliases]:
                    existing.aliases.append(alias)
                self.alias_map[cleaned_a] = target_id
            # Merge summaries if missing
            if not existing.summary_en and entity.summary_en:
                existing.summary_en = entity.summary_en
            if not existing.summary_hi and entity.summary_hi:
                existing.summary_hi = entity.summary_hi
            return

        # New entity registration
        self.entities[entity.entity_id] = entity
        self.alias_map[entity.canonical_name.lower()] = entity.entity_id
        for alias in entity.aliases:
            self.alias_map[alias.lower()] = entity.entity_id

    def get_entity_by_alias(self, alias: str) -> Optional[KnowledgeEntity]:
        """Resolves an alias to a canonical entity."""
        cleaned = alias.strip().lower()
        entity_id = self.alias_map.get(cleaned)
        if entity_id:
            return self.entities.get(entity_id)
        return None

    def search_entities(self, query: str) -> List[Tuple[KnowledgeEntity, float]]:
        """Searches entities returning matched entities with match confidence."""
        cleaned = query.strip().lower()
        results: List[Tuple[KnowledgeEntity, float]] = []

        # 1. Exact alias match
        if cleaned in self.alias_map:
            ent = self.entities[self.alias_map[cleaned]]
            return [(ent, 1.0)]

        # 2. Word boundary matching in aliases (prevents false matches like 'sona' inside 'personal')
        for alias, ent_id in self.alias_map.items():
            if alias == cleaned:
                results.append((self.entities[ent_id], 1.0))
            else:
                pattern = r"\b" + re.escape(alias) + r"\b"
                if re.search(pattern, cleaned):
                    if alias in ("who", "it", "is", "in", "on", "at", "to", "as", "by", "for", "an", "a"):
                        continue
                    # Short aliases (<= 2 chars e.g. 'au', 'fe', 'cu', 'o') require chemical/symbol context
                    if len(alias) <= 2 and not any(k in cleaned for k in ("symbol", "element", "formula", "tatva")):
                        continue
                    conf = 0.90 if len(alias) >= 4 else 0.80
                    results.append((self.entities[ent_id], conf))

        # Deduplicate by entity_id taking max confidence
        deduped: Dict[str, Tuple[KnowledgeEntity, float]] = {}
        for ent, conf in results:
            if ent.entity_id not in deduped or conf > deduped[ent.entity_id][1]:
                deduped[ent.entity_id] = (ent, conf)

        return sorted(deduped.values(), key=lambda x: x[1], reverse=True)

    def learn_fact(self, entity_id: str, property_name: str, value: Any, category: KnowledgeCategory = KnowledgeCategory.GENERAL) -> bool:
        """Allows dynamic learning and updating of entity properties."""
        entity = self.entities.get(entity_id)
        if not entity:
            # Create a new entity if missing
            entity = KnowledgeEntity(
                entity_id=entity_id,
                canonical_name=entity_id.replace("_", " ").title(),
                entity_type="learned_entity",
                categories=[category],
                properties={property_name: value}
            )
            self.add_entity(entity)
            logger.info(f"Learned new entity [{entity_id}] with {property_name} = {value}")
            return True

        entity.properties[property_name] = value
        if category not in entity.categories:
            entity.categories.append(category)
        logger.info(f"Updated entity [{entity_id}] property {property_name} = {value}")
        return True
