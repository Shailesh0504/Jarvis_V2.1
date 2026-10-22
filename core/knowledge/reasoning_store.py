# core/knowledge/reasoning_store.py
"""
Conceptual and scientific reasoning repository for the Jarvis Knowledge Engine.
Provides bilingual (English & Hindi/Hinglish) conceptual models for 'Why', 'How', and 'Explain' questions.
"""

from typing import Dict, List, Optional, Tuple
import re
from .models import ConceptReasoning


_REASONING_CONCEPTS: List[ConceptReasoning] = [
    ConceptReasoning(
        concept_id="blue_sky",
        title="Why the Sky Appears Blue",
        category="physics_optics",
        simple_explanation_en="The sky appears blue because of Rayleigh scattering. Earth's atmosphere scatters shorter wavelength blue light more than other colors in sunlight.",
        simple_explanation_hi="Aasman neela isliye dikhta hai kyunki atmospheric scattering ki wajah se suraj ki roshni mein se blue light sabse zyada scatter hoti hai.",
        detailed_explanation_en="Sunlight reaches Earth's atmosphere and is scattered in all directions by all the gases and particles in the air. Blue light travels as smaller, shorter waves than other colors, so it is scattered more frequently by oxygen and nitrogen molecules in the atmosphere.",
        detailed_explanation_hi="Suraj ki safed roshni saat rangon se bani hoti hai. Blue light ki wavelength chhoti hone ke karan hawa ke molecules use charo taraf bikhra dete hain, jisse hume aasman neela dikhta hai.",
        key_principles=["Rayleigh scattering", "Wavelength of blue light", "Atmospheric molecules"],
        keywords=["sky blue", "sky appear blue", "aasman neela", "aasman blue", "aakash neela", "why sky is blue", "sky color"]
    ),
    ConceptReasoning(
        concept_id="photosynthesis",
        title="Photosynthesis",
        category="biology",
        simple_explanation_en="Photosynthesis is the biological process by which green plants use sunlight, water, and carbon dioxide to produce oxygen and glucose for energy.",
        simple_explanation_hi="Photosynthesis woh process hai jisme green plants sunlight, water aur carbon dioxide ki help se apna food banate hain aur oxygen release karte hain.",
        detailed_explanation_en="In plant leaves, chlorophyll absorbs sunlight. This energy transforms water absorbed by roots and carbon dioxide absorbed from the air into glucose (plant food) and releases oxygen gas as a byproduct.",
        detailed_explanation_hi="Ped-paudhon ki pattiyon mein chlorophyll hota hai jo dhoop ko absorb karta hai. Paani aur carbon dioxide ke sath milkar yeh glucose banata hai aur oxygen gas chhodta hai.",
        key_principles=["Chlorophyll", "Sunlight", "Carbon Dioxide", "Water", "Glucose & Oxygen"],
        keywords=["photosynthesis", "prakash sanshleshan", "plants make food", "paudhe khana kaise banate hain"]
    ),
    ConceptReasoning(
        concept_id="gravity",
        title="Gravity",
        category="physics",
        simple_explanation_en="Gravity is the universal attractive force by which a planet or other mass draws objects toward its center.",
        simple_explanation_hi="Gravity ya gurutwakarshan ek aisi natural force hai jo har mass ya vastu ko apni taraf kheenchti hai.",
        detailed_explanation_en="Gravity keeps all planets in orbit around the Sun and holds Earth's atmosphere, oceans, and people firmly on the surface. Massive objects create stronger gravitational pulls.",
        detailed_explanation_hi="Gravity ki wajah se hi hum zameen par tike rehte hain aur sabhi grah suraj ke charo taraf chakkar lagate hain. Sir Isaac Newton ne iska pata lagaya tha.",
        key_principles=["Mass attracts mass", "Inverse square law", "Planetary orbits"],
        keywords=["gravity", "gurutwakarshan", "gurutva", "what is gravity", "explain gravity"]
    ),
    ConceptReasoning(
        concept_id="stars_twinkle",
        title="Why Stars Twinkle",
        category="astronomy_optics",
        simple_explanation_en="Stars twinkle due to atmospheric refraction. Light from distant point-like stars bends continuously through shifting layers of Earth's air.",
        simple_explanation_hi="Taare atmospheric refraction ke karan timtimate hain, kyunki hawa ke badalte temperature aur density se unka light path bend hota rehta hai.",
        detailed_explanation_en="As starlight passes through turbulent layers of Earth's atmosphere with varying temperatures and densities, the light rays are repeatedly refracted, making the star appear to shift slightly in brightness and position.",
        detailed_explanation_hi="Earth ke atmosphere mein hawa ki layers lagatar chalti aur garm-thandi hoti rehti hain, jisse taaro se aane wali roshni bend hoti hai aur hume timtimate dikhte hain.",
        key_principles=["Atmospheric refraction", "Point source of light", "Varying atmospheric density"],
        keywords=["stars twinkle", "taare timtimate", "tare timtimate", "why do stars twinkle", "stars flicker"]
    ),
    ConceptReasoning(
        concept_id="atom",
        title="What is an Atom",
        category="chemistry_physics",
        simple_explanation_en="An atom is the fundamental building block of all ordinary matter, composed of protons, neutrons, and orbiting electrons.",
        simple_explanation_hi="Atom ya parmanu kisi bhi padarth ki sabse basic unit hoti hai, jo protons, neutrons aur electrons se bani hoti hai.",
        detailed_explanation_en="Atoms consist of a dense central nucleus containing positively charged protons and neutral neutrons, surrounded by a cloud of negatively charged electrons.",
        detailed_explanation_hi="Atom ke center mein nucleus hota hai jisme protons aur neutrons hote hain, aur electrons uske charo taraf orbit karte hain.",
        key_principles=["Protons", "Neutrons", "Electrons", "Nucleus"],
        keywords=["atom kya hai", "what is an atom", "what is atom", "parmanu kya hai", "atom"]
    ),
    ConceptReasoning(
        concept_id="rainbow",
        title="How a Rainbow Forms",
        category="optics_meteorology",
        simple_explanation_en="A rainbow forms when sunlight enters raindrops and undergoes refraction, internal reflection, and dispersion into its spectrum of colors.",
        simple_explanation_hi="Indradhanush tab banta hai jab suraj ki roshni baarish ki boondo mein enter karti hai aur refraction tatha dispersion se saat rangon mein bat jaati hai.",
        detailed_explanation_en="Each raindrop acts as a tiny prism. As white sunlight enters the droplet, it refracts, reflects off the inner surface of the drop, and separates into the visible spectrum: Violet, Indigo, Blue, Green, Yellow, Orange, Red (VIBGYOR).",
        detailed_explanation_hi="Pani ki boondein prism ki tarah kaam karti hain jo suraj ki roshni ko saat rangon VIBGYOR mein divide kar deti hain.",
        key_principles=["Refraction", "Internal Reflection", "Dispersion", "VIBGYOR"],
        keywords=["rainbow", "indradhanush", "how rainbow forms", "indradhanush kaise banta hai"]
    ),
    ConceptReasoning(
        concept_id="black_hole",
        title="What is a Black Hole",
        category="astrophysics",
        simple_explanation_en="A black hole is a region in spacetime where gravity is so immensely strong that nothing, not even light, can escape from it.",
        simple_explanation_hi="Black hole antariksh mein ek aisi jagah hai jahan gravity itni zyada powerful hoti hai ki roshni bhi usse bahar nahi nikal sakti.",
        detailed_explanation_en="Black holes form when extremely massive stars collapse at the end of their lifecycle. The boundary beyond which nothing can escape is called the event horizon.",
        detailed_explanation_hi="Jab koi bada tara khatam hota hai aur collapse ho jata hai, tab black hole banta hai. Iske boundary ko event horizon kehte hain.",
        key_principles=["Singularity", "Event horizon", "Escape velocity exceeds speed of light"],
        keywords=["black hole", "blackhole", "what is black hole", "black hole kya hota hai"]
    ),
    ConceptReasoning(
        concept_id="eclipse",
        title="Solar and Lunar Eclipses",
        category="astronomy",
        simple_explanation_en="An eclipse occurs when a celestial body moves into the shadow of another, such as when the Moon passes between the Sun and Earth (Solar Eclipse).",
        simple_explanation_hi="Grahan tab lagta hai jab Surya, Prithvi aur Chandrama ek seedh mein aa jaate hain aur ek ki chhaya doosre par padti hai.",
        detailed_explanation_en="In a Solar Eclipse (Surya Grahan), the Moon blocks the Sun's light from reaching Earth. In a Lunar Eclipse (Chandra Grahan), Earth comes between the Sun and Moon, casting its shadow on the Moon.",
        detailed_explanation_hi="Surya Grahan mein Chandrama Surya aur Prithvi ke beech aa jata hai. Chandra Grahan mein Prithvi Surya aur Chandrama ke beech aa jaati hai.",
        key_principles=["Orbital alignment", "Solar Eclipse", "Lunar Eclipse", "Umbra and Penumbra"],
        keywords=["eclipse", "grahan", "surya grahan", "chandra grahan", "solar eclipse", "lunar eclipse"]
    ),
    ConceptReasoning(
        concept_id="artificial_intelligence",
        title="Artificial Intelligence",
        category="computer_science",
        simple_explanation_en="Artificial Intelligence (AI) is the branch of computer science focused on building smart systems capable of performing tasks that typically require human intelligence.",
        simple_explanation_hi="Artificial Intelligence ya AI computer science ki woh field hai jo machines ko human jaise sochne, seekhne aur decision lene ke kaabil banati hai.",
        detailed_explanation_en="AI encompasses machine learning, natural language processing, computer vision, and robotics to solve complex problems and automate reasoning.",
        detailed_explanation_hi="AI mein machine learning aur deep learning shaamil hain, jisse computers data se seekh kar voice, vision aur problem solving automate karte hain.",
        key_principles=["Machine Learning", "Neural Networks", "Natural Language Processing"],
        keywords=["artificial intelligence", "ai kya hai", "what is ai", "ai kya hota hai", "artificial intelligence kya hai"]
    ),
    ConceptReasoning(
        concept_id="dna",
        title="What is DNA",
        category="genetics_biology",
        simple_explanation_en="DNA (Deoxyribonucleic Acid) is the hereditary molecule carrying the genetic instructions for the development and functioning of all living organisms.",
        simple_explanation_hi="DNA sabhi jeevon ka genetic blueprint hai jo unke sharir ki banawat aur anuwanshik gunon ki jaankari carry karta hai.",
        detailed_explanation_en="DNA is structured as a double helix composed of four chemical bases: Adenine (A), Guanine (G), Cytosine (C), and Thymine (T).",
        detailed_explanation_hi="DNA ki structure double helix hoti hai aur yeh har cell ke nucleus mein paya jata hai.",
        key_principles=["Double helix", "A-T and G-C base pairs", "Genetic code"],
        keywords=["dna", "what is dna", "dna kya hai", "dna kya hota hai"]
    ),
    ConceptReasoning(
        concept_id="earth_revolution",
        title="Earth's Revolution Around the Sun",
        category="astronomy",
        simple_explanation_en="Earth completes one revolution around the Sun in approximately 365 days and 6 hours (365.25 days), which constitutes one calendar year.",
        simple_explanation_hi="Prithvi ko Surya ka ek poora chakkar lagane mein lagbhag 365 din aur 6 ghante (365.25 din) ka samay lagta hai.",
        detailed_explanation_en="Earth orbits the Sun at an average speed of about 29.78 km/s. The extra 6 hours each year accumulate to create a Leap Day every 4 years.",
        detailed_explanation_hi="Prithvi lagbhag 29.78 km/s ki speed se surya ke charo taraf ghumti hai. Yeh bache hue 6 ghante har 4 saal mein judkar Leap Day banate hain.",
        key_principles=["Orbital period", "Leap year", "Solar orbit"],
        keywords=["prithvi suraj ka chakkar", "earth revolution", "earth orbit", "prithvi surya ka chakkar", "chakkar lagati hai", "revolution of earth", "prithvi kitne din mein chakkar", "chakkar lagane mein kitna time", "suraj ke charo taraf", "surya ke charo taraf"]
    ),
    ConceptReasoning(
        concept_id="rain_formation",
        title="How Rain Forms",
        category="meteorology",
        simple_explanation_en="Rain forms through the water cycle: evaporation of surface water, condensation into cloud droplets in the atmosphere, and precipitation when droplets become heavy.",
        simple_explanation_hi="Baarish water cycle se hoti hai: suraj ki garmi se paani bhaap banker upar uthta hai, condense hokar baadal banta hai, aur bhaari hone par boondon ke roop mein girta hai.",
        detailed_explanation_en="Solar energy evaporates water from oceans and lakes. As moisture rises, cooler air causes water vapor to condense on microscopic particles forming clouds. When droplets coalesce and exceed atmospheric updrafts, they fall as rain.",
        detailed_explanation_hi="Suraj ki dhoop se samundar aur nadiyon ka paani evaporate hota hai. Upar thandi hawa mein condensation se baadal bante hain aur jab yeh boondein badi aur bhaari ho jaati hain toh baarish hoti hai.",
        key_principles=["Evaporation", "Condensation", "Precipitation", "Water cycle"],
        keywords=["rain kaise hoti hai", "how rain forms", "baarish kaise hoti hai", "barish kaise hoti hai", "water cycle", "how it rains", "why does it rain", "baarish kyun hoti hai"]
    ),
    ConceptReasoning(
        concept_id="airplane_flight",
        title="How Airplanes Fly",
        category="aerodynamics_physics",
        simple_explanation_en="Airplanes fly by generating aerodynamic lift with their specially shaped wings (airfoils) following Bernoulli's principle and Newton's third law of motion, which overcomes their weight.",
        simple_explanation_hi="Hawai jahaz apne wings (airfoil design) ki wajah se udte hain; wings ke upar hawa tezi se chalti hai jisse low pressure banta hai aur neeche se aerodynamic lift milti hai jo gravity ko overcome karti hai.",
        detailed_explanation_en="Airplane wings are curved on top and flatter on the bottom. As the engines thrust the plane forward, air moves faster over the top surface, creating lower pressure above and higher pressure beneath (Bernoulli's principle). Additionally, the wings deflect incoming air downward, producing an equal and opposite upward reaction force (Newton's third law) called lift.",
        detailed_explanation_hi="Hawai jahaz ke wings ko airfoil shape mein banaya jata hai. Engine ki forward thrust se jab plane tezi se aage badhta hai, toh wings ke aakaar ki wajah se upar hawa ka pressure kam aur neeche zyada ho jata hai, jisse jahaz hawa mein upar uth jata hai.",
        key_principles=["Aerodynamic lift", "Airfoil wing design", "Bernoulli's principle", "Newton's third law of motion", "Thrust vs Drag"],
        keywords=["airplane kaise udta hai", "how airplanes fly", "how planes fly", "plane kaise udta hai", "hawai jahaj kaise udta hai", "why do planes fly"]
    ),
    ConceptReasoning(
        concept_id="leaves_green",
        title="Why Plant Leaves Are Green",
        category="biology_botany",
        simple_explanation_en="Plant leaves appear green because their cells contain chlorophyll, a pigment that absorbs red and blue wavelengths of sunlight for photosynthesis while reflecting green light.",
        simple_explanation_hi="Ped-paudhon ki pattiyan chlorophyll ki wajah se hari dikhti hain; chlorophyll suraj ki lal aur neeli roshni ko absorb karta hai aur hari roshni ko reflect karta hai.",
        detailed_explanation_en="During photosynthesis, plant chloroplasts utilize chlorophyll pigments to capture solar energy. Chlorophyll absorbs high-energy blue and red light very efficiently, but does not absorb green light, reflecting it back to human eyes so leaves look green.",
        detailed_explanation_hi="Photosynthesis ke dauran paudhon ke chloroplasts dhoop se urja lete hain. Unka chlorophyll pigment red aur blue colors ko absorb kar leta hai, par green color ko absorb nahi karta aur reflect kar deta hai, isliye pattiyan hari dikhti hain.",
        key_principles=["Chlorophyll pigment", "Selective light absorption", "Photosynthesis", "Reflection of green wavelengths"],
        keywords=["pattiyan hari kyun hoti hain", "why leaves are green", "why plants are green", "paudhon ki pattiyan hari", "patte hare kyun hote hain", "why leaves green"]
    ),
    ConceptReasoning(
        concept_id="sound_in_vacuum",
        title="Why Sound Cannot Travel in a Vacuum",
        category="physics_acoustics",
        simple_explanation_en="Sound cannot travel in a vacuum or outer space because it is a mechanical wave that requires a physical medium of vibrating particles (air, liquid, or solid) to propagate.",
        simple_explanation_hi="Sound ya aawaz vacuum (space) mein travel nahi kar sakti kyunki yeh ek mechanical wave hai jise failne ke liye hawa ya kisi madhyam (particles) ki zaroorat hoti hai.",
        detailed_explanation_en="Unlike light (an electromagnetic wave that travels freely through a vacuum), sound is created by vibrating atoms and molecules colliding and transferring kinetic energy. In the vacuum of deep space where matter density is near zero, sound waves have no medium to vibrate.",
        detailed_explanation_hi="Light electromagnetic wave hai jo bina kisi medium ke bhi chal sakti hai, lekin sound vibration par chalti hai. Antariksh mein hawa ya particles na hone ki wajah se aawaz aage nahi badh sakti.",
        key_principles=["Mechanical wave nature of sound", "Requirement of material medium", "Absence of vibrating matter in vacuum"],
        keywords=["space mein aawaz kyun nahi aati", "sound in vacuum", "can sound travel in space", "vacuum mein aawaz", "antariksh mein aawaz"]
    ),
    ConceptReasoning(
        concept_id="lightning_before_thunder",
        title="Why Lightning is Seen Before Thunder is Heard",
        category="physics_meteorology",
        simple_explanation_en="Lightning is seen before thunder is heard because light travels vastly faster than sound (approx 300,000 km/s for light versus 343 m/s for sound).",
        simple_explanation_hi="Bijli ki chamak garjan se pehle isliye dikhti hai kyunki light ki speed sound ki speed se laakhon guna tez (lagbhag 3 lakh km/s) hoti hai.",
        detailed_explanation_en="Although both lightning flash and thunder sound are generated at the exact same instant during a lightning strike, light travels at 299,792 km/s, reaching the observer almost instantaneously. In contrast, sound travels through air at only about 343 m/s (approx 1 km every 3 seconds).",
        detailed_explanation_hi="Aakash mein bijli aur garjan ek hi sath paida hote hain. Lekin light lagbhag 3,00,000 km per second ki speed se aati hai, jabki sound sirf 343 meter per second ki speed se chalti hai, isliye aawaz baad mein sunai deti hai.",
        key_principles=["Speed of light (300,000 km/s)", "Speed of sound (343 m/s)", "Same instant origin, differing arrival times"],
        keywords=["bijli pehle kyun dikhti hai", "lightning before thunder", "thunder and lightning", "bijli aur garjan", "why lightning first"]
    ),
    ConceptReasoning(
        concept_id="day_and_night",
        title="How Day and Night Occur",
        category="astronomy_geography",
        simple_explanation_en="Day and night occur because the Earth continuously rotates on its tilted axis from west to east once every 24 hours, exposing half the planet to sunlight while the other half faces away.",
        simple_explanation_hi="Din aur raat Prithvi ke apni dhuri (axis) par ghumne (rotation) se hote hain; jo hissa suraj ke samne hota hai wahan din aur doosre hisse par raat hoti hai.",
        detailed_explanation_en="Earth completes one full rotation around its axis every 24 hours. The side illuminated by the Sun experiences daytime, while the side in shadow experiences night. As Earth keeps spinning eastward, day turns into night seamlessly across time zones.",
        detailed_explanation_hi="Prithvi lagbhag 24 ghante mein apni axis par ek poora chakkar ghumti hai. Suraj ke samne aane wala aadha hissa dhoop pata hai jahan din hota hai, aur pichle hisse mein andhera rehta hai jahan raat hoti hai.",
        key_principles=["Earth's axial rotation", "24-hour cycle", "Illumination and shadow hemispheres"],
        keywords=["din aur raat kaise hote hain", "day and night", "why day and night", "din raat kaise bante hain", "din aur raat kyun hote hain"]
    ),
    ConceptReasoning(
        concept_id="clouds_floating",
        title="Why Clouds Float in the Sky",
        category="meteorology_physics",
        simple_explanation_en="Clouds float because they consist of billions of microscopic water droplets and ice crystals so lightweight that gentle rising thermal updrafts of warm air keep them suspended.",
        simple_explanation_hi="Baadal isliye tairte hain kyunki unki paani ki boondein itni sukshm aur halki hoti hain ki zameen se uthne wali garm hawa (updrafts) unhe aasani se sambhale rakhti hai.",
        detailed_explanation_en="Although a large cumulus cloud can contain hundreds of tons of water in total, that mass is dispersed across billions of microscopic droplets, each with an infinitesimal terminal velocity. Warm air rising from Earth's heated surface easily provides enough upward buoyancy to counteract gravity until droplets coalesce into heavy raindrops.",
        detailed_explanation_hi="Baadal mein bohot sara paani hota hai, lekin yeh paani arabon nanhi-nanhi boondon mein banta hota hai. Zameen se upar uthne wali garm hawa ki upward force in halki boondon ko neeche girne nahi deti.",
        key_principles=["Microscopic droplet size", "Thermal updrafts", "Terminal velocity", "Buoyancy"],
        keywords=["baadal kaise tairte hain", "why clouds float", "why do clouds float", "baadal hawa mein kyun", "clouds float in sky"]
    ),
    ConceptReasoning(
        concept_id="ocean_tides",
        title="Why Ocean Tides Occur",
        category="astrophysics_oceanography",
        simple_explanation_en="Ocean tides are caused primarily by the gravitational pull of the Moon and the Sun acting upon Earth's oceans as the planet rotates.",
        simple_explanation_hi="Samundar mein jwar-bhata (tides) Chandrama aur Surya ke gurutwakarshan (gravitational pull) ke karan aate hain jo samundar ke paani ko apni taraf kheenchte hain.",
        detailed_explanation_en="The Moon's gravitational force pulls water toward it, creating a tidal bulge on the side facing the Moon, while inertial centrifugal forces create a secondary bulge on the opposite side. As Earth rotates through these water bulges every 24 hours and 50 minutes, coastlines experience two high tides and two low tides daily.",
        detailed_explanation_hi="Chandrama Prithvi ke kareeb hone ki wajah se samundar ke paani ko apni taraf kheenchta hai, jisse tidal bulge banta hai aur high tide aati hai. Prithvi ke ghumne se har 24 ghante mein aamtaur par do high tides aur do low tides aati hain.",
        key_principles=["Lunar gravitational pull", "Solar gravitational influence", "Tidal bulges", "Earth's rotation"],
        keywords=["jwar bhata kyun aata hai", "ocean tides", "why tides occur", "tides kaise aati hain", "samundar mein jwar bhata"]
    )
]


class ReasoningStore:
    """Stores and retrieves scientific and conceptual reasoning models."""

    def __init__(self):
        self.concepts: Dict[str, ConceptReasoning] = {}
        self.keyword_index: List[Tuple[re.Pattern, str]] = []
        self._load_seed_concepts()

    def _load_seed_concepts(self) -> None:
        for c in _REASONING_CONCEPTS:
            self.concepts[c.concept_id] = c
            for kw in c.keywords:
                pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
                self.keyword_index.append((pattern, c.concept_id))

    COMMON_STOPWORDS = {
        "kya", "hai", "hain", "what", "is", "the", "are", "ka", "ki", "ke", "mein",
        "se", "ko", "why", "how", "kyun", "kyu", "hota", "hoti", "hote", "an", "a"
    }

    def find_concept(self, query: str) -> Optional[ConceptReasoning]:
        """Finds a matching conceptual model for a query."""
        lowered = query.lower()
        # 1. Exact phrase pattern match
        for pattern, concept_id in self.keyword_index:
            if pattern.search(lowered):
                return self.concepts.get(concept_id)

        # 2. Token set match for multi-word concepts (excluding common question stopwords)
        for c in self.concepts.values():
            for kw in c.keywords:
                tokens = [t for t in kw.lower().split() if t not in self.COMMON_STOPWORDS and len(t) >= 3]
                if tokens and len(tokens) >= 2 and all(re.search(r"\b" + re.escape(tok) + r"\b", lowered) for tok in tokens):
                    return c
        return None
