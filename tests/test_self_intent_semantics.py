# tests/test_self_intent_semantics.py
"""Semantic paraphrase dataset + acceptance tests for the ASSISTANT_* self-intent layer.

10 intents x 100 variations (Hindi / Hinglish / English / short / typos /
grammar mistakes / casual / formal / STT mistakes). Single owner of this
dataset: core/semantic/self_intents.py.
"""

import pytest

from core.semantic.self_intents import SelfIntent, detect_self_intent

# ---------------------------------------------------------------------------
# 100 variations per intent
# ---------------------------------------------------------------------------

IDENTITY_100 = [
    "aap ka naam kya hai?", "tumhara naam kya hai?", "tumhara naam kya h", "what is your name?",
    "what's your name?", "who are you?", "aap kaun ho?", "tum kaun ho?",
    "who r u?", "ur name?", "naam batao", "naam kya hai?",
    "apna naam batao", "what should I call you?", "main tumhe kya bulaun?", "tumhara naam kya hai",
    "aapka naam kya hai", "tumara naam kya hai", "tumhara nam kya h", "tumhara naam kya hain",
    "aap ka naam kya h", "tera naam kya hai", "tumhara naam batao", "apna naam batao na",
    "naam kya hai tumhara", "naam batao apna", "tumhara naam?", "aapka naam?",
    "your name?", "naam?", "tumhara naam kya he", "tumhara naam kya hy",
    "tmhara naam kya hai", "tumhra naam kya hai", "aap ka nam kya hai", "aapka nam kya hai",
    "who are u?", "who r you?", "who are you", "what is ur name",
    "wat is ur name", "wht is ur name", "what is your name", "whats your name",
    "what's ur name", "tell me your name", "tell me about yourself", "introduce yourself",
    "your name please", "your name batao", "aapka naam bataiye", "tumhara naam bataiye",
    "tu kaun hai?", "tu kaun hai", "tum kon ho", "aap kon ho",
    "tumhe kya bulaun", "main tumhe kya bulaun", "tumko kya bulaun", "what should i call you",
    "can i know your name", "may i know your name", "aapka parichay dijiye", "apna parichay do",
    "tumhara parichay kya hai", "jarvis tumhara naam kya hai", "jarvis aapka naam kya hai", "bhai tumhara naam kya hai",
    "sir aapka naam kya hai", "boss tumhara naam kya hai", "please apna naam batao", "zara naam batao",
    "yaar tumhara naam kya hai", "hello tumhara naam kya hai", "sunao tumhara naam kya hai", "achha tumhara naam kya hai",
    "toh tumhara naam kya hai", "tumhara naam kya hai batao", "tumhara naam kya hai ji", "aap kaun ho ji",
    "tum kaun ho bhai", "who are you boss", "aap ka naam kya hai ji", "tumhara shubh naam kya hai",
    "aapka shubh naam kya hai", "tumhara naam kya hai??", "TUMHARA NAAM KYA HAI", "What Is Your Name",
    "WHO ARE YOU", "tumhara naam kya hai.", "aap ka naam kya hai.", "naam batao!",
    "apna naam batao!", "your name", "tumhara naam kya hai na", "aap kaun hain",
    "tum kaun ho na", "who r u", "ur name", "naam kya h",
]

CREATOR_100 = [
    "tum ko kisne banaya?", "tumhe kisne banaya?", "aapko kisne banaya?", "who created you?",
    "who create you?", "who made you?", "who built you?", "who developed you?",
    "who is your creator?", "tumhara creator kaun hai?", "tumhe kisne develop kiya?", "tumhe kisne banaya hai?",
    "who made this assistant?", "ye JARVIS kisne banaya?", "JARVIS ko kisne develop kiya?", "tum kaha se aaye?",
    "how were you created?", "tumko kisne banaya", "tum ko kisne bnaya", "tumhe kisne bnaya",
    "tumhe kis ne banaya", "tumko kis ne banaya", "aap ko kisne banaya", "aapko kisne bnaya",
    "tujhe kisne banaya", "tera creator kaun hai", "tumhara creator kon hai", "tumhara creator kaun h",
    "creator kaun hai tumhara", "who created u?", "who create u?", "who made u?",
    "who built u?", "who developed u?", "who creatd you", "who creted you",
    "who crate you", "who bulit you", "who biult you", "who devlop you",
    "who made you", "where did you come from", "where did u come from", "how were u created",
    "tum kahan se aaye", "tum kaha se aaye ho", "aap kahan se aaye", "tumhe kisne banaya hai",
    "tumko kisne banaya hai", "tumhe kisne banaya tha", "tumhe kisne create kiya", "tumhe kisne develop kiya hai",
    "tumko kisne develop kiya", "aapko kisne develop kiya", "jarvis ko kisne banaya", "jarvis ko kisne bnaya",
    "jarvis tumko kisne banaya", "jarvis tumhe kisne banaya", "ye jarvis kisne banaya hai", "is assistant ko kisne banaya",
    "tumhein kisne banaya", "tumhen kisne banaya", "bhai tumhe kisne banaya", "sir aapko kisne banaya",
    "boss tumko kisne banaya", "please batao tumhe kisne banaya", "zara batao kisne banaya tumhe", "tumko kisne banaya hai ji",
    "aapko kisne banaya hai ji", "TUMHE KISNE BANAYA", "Who Created You", "WHO MADE YOU",
    "tumhe kisne banaya??", "tum ko kisne banaya.", "who made you!", "tumhara janmdata kaun hai",
    "tumhara nirmata kaun hai", "tumhe kisne nirmit kiya", "aapka creator kaun hai", "tumhara banane wala kaun hai",
    "tum kisne banaye ho", "tumhe banaya kisne", "banaya kisne tumhe", "kisne banaya tumko",
    "kisne banaya hai tumhe", "tumhe kisne banaya batao", "batao tumhe kisne banaya", "sunao kisne banaya tumhe",
    "arey tumhe kisne banaya", "achha tumhe kisne banaya", "toh tumhe kisne banaya", "tumko banane wala kaun",
    "tumhare creator ka naam kya hai", "who is ur creator", "wat made you", "wht created you",
    "hu made you", "tum kaha se aae", "tum kahan se aae ho", "aap kaha se aaye ho",
]

CAPABILITIES_100 = [
    "tum kya kar sakte ho?", "what can you do?", "tumhare capabilities kya hain?", "what are you capable of?",
    "mere liye kya kar sakte ho?", "tum kya kya kar sakte ho", "what can u do", "wat can you do",
    "wht can u do", "tum kya kar sakti ho", "aap kya kar sakte hain", "aap kya kya kar sakte hain",
    "tum kya kar sakte ho", "tum kya kya kar sakti ho", "mere liye kya kar sakti ho", "mere liye kya kar sakte ho",
    "tum mere liye kya kya kar sakte ho", "tumhare capabilities kya hai", "tumhari capabilities kya hain", "aapki capabilities kya hain",
    "what are your capabilities", "what are u capable of", "tell me your capabilities", "what are you capable of",
    "tumhari kshamta kya hai", "tum kya karne me saksham ho", "tum me kya kya features hain", "tumhare features kya hain",
    "tumhare functions kya hain", "tum kya kya kar sakte ho batao", "batao tum kya kar sakte ho", "jarvis tum kya kar sakte ho",
    "jarvis what can you do", "bhai tum kya kar sakte ho", "sir aap kya kar sakte hain", "boss tum kya kya kar sakte ho",
    "please batao kya kar sakte ho", "TUM KYA KAR SAKTE HO", "What Can You Do", "WHAT ARE YOU CAPABLE OF",
    "tum kya kar sakte ho??", "tum kya kar sakte ho.", "what can you do!", "tum se kya kya ho sakta hai",
    "tumse kya ho sakta hai", "aapse kya kya ho sakta hai", "what tasks can you do", "what tasks can u perform",
    "tum kaun kaun se kaam kar sakte ho", "tum kaun se kaam kar sakte ho", "kaun se kaam kar sakte ho tum", "tumhari services kya hain",
    "tum kya seva de sakte ho", "aap kya seva de sakte hain", "tum kisme madad kar sakte ho", "kin cheezon me help kar sakte ho",
    "what help can you give", "tum kya help kar sakte ho", "kya kya kar sakte ho", "kya kya kar sakti ho",
    "kar kya sakte ho tum", "tumhara kaam kya hai", "tumhara kaam kya kya hai", "aapka karya kya hai",
    "what is your purpose", "what is ur purpose", "tumhara uddeshya kya hai", "tum kis kaam aate ho",
    "tum kis kaam ke ho", "tumse kya fayda hai", "what can i ask you to do", "main tumse kya kara sakta hoon",
    "main tumse kya kya kara sakta hoon", "tum kya kya sambhal sakte ho", "tum kitna kuch kar sakte ho", "tumhari limits kya hain",
    "tumhari seema kya hai", "kahan tak help kar sakte ho", "how can you help me", "how can u help me",
    "tum meri kaise help kar sakte ho", "tum meri kya help kar sakte ho", "meri kya madad kar sakte ho", "show me your skills",
    "tumhare skills kya hain", "tum me kya hunar hai", "tum kya kya jaante ho", "what do you know how to do",
    "tumhe kya kya aata hai", "tumko kya kya aata hai", "aapko kya kya aata hai", "list your features",
    "apne features batao", "apne kaam ginwao", "ek ek karke batao kya kar sakte ho", "vistar se batao kya kar sakte ho",
    "detail me batao capabilities", "can you help me", "can u help me", "could you help me",
]

STATUS_100 = [
    "tum kaise ho?", "how are you?", "aap kaise ho?", "kya haal hai?",
    "tum theek ho?", "are you ok?", "tum kaise ho", "aap kaise hain",
    "kaise ho tum", "kaise ho aap", "how r u", "how are u",
    "how are you", "how r you", "kya haal hain", "kya haal hai tumhara",
    "aur batao kya haal hai", "tumhara haal kya hai", "aapka haal kya hai", "tum theek ho na",
    "aap theek hain", "tum theek thaak ho", "tum poori tarah theek ho", "tum swasth ho",
    "tum badhiya ho", "are you fine", "are you good", "are you okay",
    "r u ok", "r u fine", "tumhara kya chal raha hai", "tumhara kya haal hai",
    "kaise ho bhai", "kaise ho sir", "jarvis tum kaise ho", "jarvis how are you",
    "hello kaise ho", "aur kaise ho", "toh kaise ho", "tum kaise ho ji",
    "aap kaise hain ji", "TUM KAISE HO", "How Are You", "ARE YOU OK",
    "tum kaise ho??", "how are you!", "tum kaise ho.", "kese ho tum",
    "tum kese ho", "tum kase ho", "tum khush ho", "aap khush hain",
    "tumhara mood achha hai", "tumhara mood kaisa hai", "tum bilkul sahi ho", "tum sahi ho",
    "tum ekdum fit ho", "tum fit ho", "aap fit hain", "tum healthy lag rahe ho",
    "tum healthy ho", "tum batao kaam kaisa chal raha hai", "tumhara kaam kaisa chal raha hai", "tum full mast ho",
    "tum mast lag rahe ho", "tum mast ho", "tum bahut badhiya ho", "tum badhiya ho na",
    "tum ekdum badhiya lag rahe ho", "tum ekdum badhiya ho", "tum sunao haal chaal kya hai", "apna haal chaal batao",
    "apna haal batao", "tumhara haal chaal kya hai", "are you well", "are you doing well",
    "hope you are well",     "tum achhe ho", "aap achhe hain", "tabeeyat kaisi hai tumhari",
    "tumhari tabeeyat kaisi hai", "tum thak toh nahi gaye", "tum thake toh nahi", "tumne aaram kar liya",
    "tumne rest kiya", "tum soye the", "tumhe neend aayi", "tumhari neend hui",
    "tum taaza ho", "tum fresh ho", "tum full energy me ho", "tum energetic ho",
    "kaise mehsoos kar rahe ho", "how are you feeling", "how r u feeling", "tum kaisa feel kar rahe ho",
    "aap kaisa mehsoos kar rahe hain", "tum ekdum first class ho", "tum first class ho", "tum jhakaas ho",
]

GREETING_100 = [
    "hello", "hi", "hey", "namaste",
    "namaskar", "good morning", "good afternoon", "good evening",
    "hello jarvis", "hi jarvis", "hey jarvis", "namaste jarvis",
    "ram ram", "pranam", "sat sri akal", "adaab",
    "good morning jarvis", "good evening jarvis", "hello boss", "hi boss",
    "hey boss", "namaste boss", "hello ji", "namaste ji",
    "good morning boss", "good day", "hello hello", "hii",
    "helo", "hallo", "helllo", "hey there",
    "hello there", "hi there", "namaste dost", "hello dost",
    "hey dost", "namaste bhai", "hello bhai", "good morning bhai",
    "shubh prabhat", "suprabhat", "good night", "shubh ratri",
    "good afternoon boss", "good evening boss", "hey good morning", "hello good morning",
    "hi good morning", "namaste sir", "hello sir", "good morning sir",
    "pranam boss", "ram ram bhai", "ram ram jarvis", "hello friend",
    "hi friend", "hey friend", "hello dear", "hi dear",
    "namaste dear", "GOOD MORNING", "Hello", "HELLO",
    "Hi", "Namaste", "hello!", "hi!",
    "hey!", "namaste!", "good morning!", "hello?",
    "namaste ji boss", "hello jarvis boss", "hi jarvis boss", "hey jarvis boss",
    "good morning jarvis boss", "namaste jarvis boss", "hello mere dost", "hi mere dost",
    "namaste mere bhai", "hey suno", "hello suno", "hi suno",
    "good morning suno", "namaste sabko", "hello everyone", "hi everyone",
    "hey guys", "hello guys", "yo", "yo jarvis",
    "good day jarvis", "good day boss", "shubh din", "shubh din jarvis",
    "namaskar jarvis", "namaskar boss", "pranam jarvis", "adaab jarvis",
]

HELP_100 = [
    "help chahiye", "meri help karo", "madad karo", "help karo",
    "help", "madad", "sahayata ki guhaar hai", "help me",
    "mujhe help chahiye", "meri madad karo", "help kardo", "madad kardo",
    "help kar do", "madad kar do", "help karo na", "madad karo na",
    "please help karo", "please meri help karo", "kripya madad karo", "help me out",
    "help me please", "i need help", "mujhe madad chahiye", "mujhe sahayata chahiye",
    "sahayata karo", "guide karo", "mujhe guide karo", "guide kardo",
    "how to use you", "how to use u", "tumhe kaise use karun", "tumko kaise use karun",
    "kaise use karun", "jarvis help", "jarvis help karo", "jarvis meri help karo",
    "bhai help karo", "sir help karo", "boss help karo", "yaar help karo",
    "dost help karo", "HELP", "Help Chahiye", "MADAD KARO",
    "help chahiye!", "help karo!", "madad karo!", "help chahiye?",
    "ek help chahiye", "thodi help chahiye", "zara help karo", "help karoge",
    "kya tum help karoge", "kya aap madad karenge", "madad karenge", "madad ki guhaar hai",
    "sahayata dijiye", "helping hand chahiye", "madadgaar bano", "mujhe tumhari help chahiye",
    "mujhe aapki madad chahiye", "tumhari help chahiye", "aapki madad chahiye", "madad ki darkhast hai",
    "help ki darkhast hai", "sahayata ki darkhast hai", "need some help", "need help",
    "mujhe zaroorat hai help ki", "sahayta chahiye", "sahaayta karo", "support karo",
    "mujhe support karo", "support chahiye", "assist karo", "mujhe assist karo",
    "assistance chahiye", "need assistance", "help karna", "madad karna",
    "help kar dijiye", "madad kar dijiye", "kripya sahayata karein", "meharbani karke help karo",
    "bhai thodi madad karo", "yaar ek help kar", "dost help kar de", "sunao help karoge",
    "arey help karo", "achha help karo", "toh help karo", "ab help karo",
    "jaldi help karo", "turant madad karo", "foran madad karo", "help karo ji",
    "madad karo ji", "please help me", "please help", "kindly help",
]

MEMORY_100 = [
    "tumhari memory kaise kaam karti hai", "do you remember?", "tumhari memory kaise kaam karti h", "aapki memory kaise kaam karti hai",
    "your memory kaise kaam karti hai", "do you remember me", "do u remember", "kya tumhe yaad hai",
    "kya aapko yaad hai", "yaad rakhte ho", "kya tum yaad rakhte ho", "tumhe yaad rehta hai",
    "tumhari yaaddasht kaisi hai", "your memory how does it work", "how does your memory work", "how does ur memory work",
    "memory kaise kaam karti hai", "memory kaisi hai tumhari", "tum kitna yaad rakhte ho", "tum sab yaad rakhte ho",
    "kya tum bhool jaate ho", "tum bhoolte toh nahi", "do you forget things", "do u forget",
    "tumhe sab yaad rehta hai", "meri baatein yaad hain", "kya meri baat yaad hai", "kal ki baat yaad hai",
    "do you remember yesterday", "jarvis tumhari memory kaisi hai", "jarvis do you remember", "bhai yaad hai",
    "sir yaad hai", "boss yaad rakhte ho", "TUMHARI MEMORY KAISI HAI", "Do You Remember",
    "DO U REMEMBER", "tumhari memory kaise kaam karti hai?", "do you remember!", "kya tumhe meri baat yaad hai",
    "kya aapko meri baat yaad hai", "tumhe mera naam yaad hai", "kya tumhe mera naam yaad hai", "mera naam yaad hai",
    "tumhe sab kuch yaad hai", "tum kitni baatein yaad rakh sakte ho", "memory capacity kya hai", "tumhari memory capacity kya hai",
    "how much can you remember", "how much do you remember", "tum purani baatein yaad rakhte ho", "purani chats yaad hain",
    "do you remember old chats", "pichli baat yaad hai", "last time ki baat yaad hai", "tumhe context yaad rehta hai",
    "context yaad rakhte ho", "conversation yaad rehti hai", "do you remember conversations", "tumhara dimag kaisa hai",
    "tumhara dimaag kaisa hai", "yaaddasht tez hai", "tumhari yaaddasht tez hai", "bhoolne ki bimari toh nahi",
    "tum bhoolakkad toh nahi", "are you forgetful", "r u forgetful", "memory sharp hai",
    "tumhari memory sharp hai", "tumhe cheezein yaad rehti hain", "kya tumhe chehre yaad hain", "tum pehchante ho",
    "kya tum mujhe pehchante ho", "do you recognise me", "do you recognize me", "tum mujhe jaante ho",
    "kya tum mujhe jaante ho", "meri pehchan yaad hai", "tumhe meri pehchan hai", "yaadon ka kya scene hai",
    "memory ka kya scene hai", "tumhara memory system kya hai", "kaunsi memory use karte ho", "which memory do you use",
    "tumhari smriti kaisi hai", "smriti kaise kaam karti hai", "yaad karne ka tarika kya hai", "how do you memorize things",
    "tum kaise yaad rakhte ho", "aap kaise yaad rakhte hain", "yaad rakhne ka funda kya hai", "memory ka funda kya hai",
    "long term yaad rakhte ho", "do you have long term memory", "short term memory hai", "do you have short term memory",
    "kya tumhe sab kuch yaad rehta hai", "tumhari smaran shakti kaisi hai", "do you have a good memory", "r u good at remembering",
]

LANGUAGE_100 = [
    "kaun si bhasha samajhte ho", "which languages do you understand", "hindi samajhte ho", "hinglish samajhte ho",
    "language samajhte ho", "kaunsi bhasha samajhte ho", "konsi bhasha samajhte ho", "kaun si bhasha samajhte ho?",
    "which language do you understand", "what languages do you understand", "what languages do u understand", "which languages",
    "hindi samajhte ho kya", "kya hindi samajhte ho", "kya aap hindi samajhte hain", "english samajhte ho",
    "kya english samajhte ho", "hinglish samajhte ho kya", "kya hinglish samajhte ho", "tumhe hindi aati hai",
    "kya tumhe hindi aati hai", "tumhe english aati hai", "kya tumhe english aati hai", "tum kaunsi language bolte ho",
    "tum kaun si language bolte ho", "which language do you speak", "what language do you speak", "tum hindi bolte ho",
    "kya tum hindi bolte ho", "tum english bolte ho", "kya tum english bolte ho", "tumhe kaunsi bhasha aati hai",
    "tumko kaunsi language aati hai", "aapko kaunsi bhasha aati hai", "jarvis hindi samajhte ho", "jarvis which language",
    "bhai hindi aati hai", "KAUN SI BHASHA", "Which Languages", "hindi samajhte ho?",
    "which languages do you understand?", "tum hindi me baat kar sakte ho", "kya hindi me baat kar sakte ho", "hindi me jawab do",
    "hindi me bolo", "english me bolo", "hinglish me bolo", "tum hinglish bolte ho",
    "kya hinglish bolte ho", "tumhari bhasha kya hai", "aapki bhasha kya hai", "your language kya hai",
    "mother tongue kya hai", "tumhari mother tongue kya hai", "matribhasha kya hai", "tumhari matribhasha kya hai",
    "do you speak hindi", "do u speak hindi", "do you speak english", "do u speak english",
    "can you speak hindi", "can u speak hindi", "hindi bol sakte ho", "kya hindi bol sakte ho",
    "english bol sakte ho", "kya english bol sakte ho", "kitni bhasha jaante ho", "tum kitni bhashayein jaante ho",
    "how many languages do you know", "how many languages", "tumhe kitni language aati hai", "urdu samajhte ho",
    "kya urdu samajhte ho", "punjabi samajhte ho", "marathi samajhte ho", "tamil samajhte ho",
    "telugu samajhte ho", "bengali samajhte ho", "gujarati samajhte ho", "sanskrit samajhte ho",
    "kya sanskrit aati hai", "bhojpuri samajhte ho", "kya bhojpuri samajhte ho", "haryanvi samajhte ho",
    "pahadi samajhte ho", "tum local language samajhte ho", "regional language aati hai", "bhasha ka kya scene hai",
    "language ka kya scene hai", "hindi english dono aati hai", "kya dono bhasha aati hai", "multilingual ho",
    "kya tum multilingual ho", "are you multilingual", "r u multilingual", "kannada samajhte ho",
    "malayalam samajhte ho", "odia samajhte ho", "assamese samajhte ho", "tumhe har bhasha aati hai",
]

OFFLINE_100 = [
    "tum offline chal sakte ho", "do you work offline", "tum offline chal sakte ho?", "bina internet ke chal sakte ho",
    "without internet kaam kar sakte ho", "internet chahiye", "do u work offline", "kya tum offline ho",
    "tum offline ho", "aap offline hain", "kya bina internet chaloge", "bina internet chal sakte ho",
    "without internet chal sakte ho", "internet ke bina kaam karte ho", "kya internet zaroori hai", "internet zaroori hai",
    "tumhe internet chahiye", "tum internet use karte ho kya", "kya tum internet use karte ho", "do you use internet",
    "do u use internet", "do you need internet", "do u need internet", "offline mode hai",
    "kya offline mode hai", "tumhara offline mode hai", "offline kaam karte ho", "kya offline kaam karte ho",
    "jarvis offline chalta hai", "jarvis do you work offline", "bhai offline chalega", "TUM OFFLINE CHAL SAKTE HO",
    "Do You Work Offline", "OFFLINE HO", "tum offline chal sakte ho!", "bina internet ke chal sakte ho?",
    "wifi ke bina chaloge", "kya wifi chahiye", "wifi chahiye", "data chahiye",
    "kya data chahiye", "mobile data lagega", "internet connection lagega", "kya connection chahiye",
    "offline me kya kya kar sakte ho", "bina net ke kya kar sakte ho", "without net what can you do", "offline capabilities kya hain",
    "offline me chaloge", "hawai jahaz me chaloge", "flight mode me chaloge", "kya flight me kaam karoge",
    "network ke bina kaam karoge", "signal ke bina chaloge", "tumhe network chahiye", "kya network chahiye",
    "tum local chalte ho", "kya tum local ho", "local mode hai", "tumhara server offline hai",
    "cloud pe ho", "kya cloud pe ho", "tum cloud use karte ho", "do you use cloud",
    "internet band ho toh chaloge", "net band ho toh kaam karoge", "wifi band ho toh chalega", "offline tayaar ho",
    "hamesha online rehte ho", "kya hamesha online ho", "are you always online", "r u always online",
    "tum kabhi offline hote ho", "offline hote ho", "internet jaane par kya hota hai", "net jaane par ruk jaoge",
    "kya net slow par chaloge", "2g par chaloge", "tumhe kitna internet chahiye", "bandwidth kitna lagta hai",
    "offline first ho", "kya tum offline first ho", "are you offline first", "bina connection ke jawab doge",
    "connection tutne par kya karoge", "reconnect kar lete ho", "do you reconnect", "internet aane par sync hote ho",
    "offline mode me kaam karoge", "bina net ke chalega", "offline me bhi jawab doge", "bina network ke chaloge",
    "network na ho toh kya karoge", "tumhe wifi ki zaroorat hai", "kya wifi ki zaroorat hai", "offline kaam karega",
    "kya offline kaam karega", "internet ke baghair chal sakte ho", "do you need wifi", "do u need wifi",
]

TECHNOLOGY_100 = [
    "tum kaise kaam karte ho", "how do you work", "tum kaise kaam karte ho?", "kaise bane ho",
    "technology kya hai", "which technology", "how do u work", "tum kaise kaam karte ho ji",
    "aap kaise kaam karte hain", "tumhara technology kya hai", "tum kis technology par ho", "which technology do you use",
    "what technology do you use", "tum kaise bane", "tum kaise bane ho", "kaise banaye gaye ho",
    "tumhara architecture kya hai", "tum kaise operate karte ho", "how do you operate", "tumhara system kya hai",
    "tum kaise chalte ho", "how do you function", "tumhara funda kya hai", "working principle kya hai",
    "tum kaise sochte ho", "how do you think", "tum kaise samajhte ho", "how do you understand",
    "jarvis tum kaise kaam karte ho", "jarvis how do you work", "bhai kaise kaam karte ho", "TUM KAISE KAAM KARTE HO",
    "How Do You Work", "TECHNOLOGY KYA HAI", "tum kaise kaam karte ho!", "tum kaise kaam karte ho.",
    "tumhara engine kya hai", "kaunsa engine use karte ho", "which engine do you use", "tum rule based ho",
    "kya tum rule based ho", "are you rule based", "tum AI ho", "kya tum AI ho",
    "are you an AI", "r u an AI", "tum robot ho", "kya tum robot ho",
    "are you a robot", "tum software ho", "kya tum software ho", "tum program ho",
    "kya tum program ho", "tum code se bane ho", "kaunse code se bane ho", "python me bane ho",
    "kya python me bane ho", "are you made in python", "tumhara code kya hai", "tum open source ho",
    "are you open source", "tumhara version kya hai", "kaunsa version hai", "what is your version",
    "whats your version", "tum updated ho", "kya tum updated ho", "are you updated",
    "tumhara update kab hua", "last update kab hua", "tum kaise seekhte ho", "how do you learn",
    "tum seekhte ho", "kya tum seekhte ho", "do you learn", "tumhe kaun sikhata hai",
    "who teaches you", "tumhara teacher kaun hai", "training kahan se mili", "where were you trained",
    "tumhe training kisne di", "tum kitne smart ho", "how smart are you", "tumhara IQ kya hai",
    "tum insaano jaise ho", "are you like humans", "tum me emotions hain", "do you have emotions",
    "kya tum me feelings hain", "tum thakte ho", "do you get tired", "tum sote ho",
    "do you sleep", "tum khate ho", "tumhe bhookh lagti hai", "tum kahan rehte ho",
    "where do you live", "tum kahan host hote ho", "where are you hosted", "tum laptop me rehte ho",
]

DATASET = {
    SelfIntent.ASSISTANT_IDENTITY: IDENTITY_100,
    SelfIntent.ASSISTANT_CREATOR_ORIGIN: CREATOR_100,
    SelfIntent.ASSISTANT_CAPABILITIES: CAPABILITIES_100,
    SelfIntent.ASSISTANT_STATUS: STATUS_100,
    SelfIntent.ASSISTANT_GREETING: GREETING_100,
    SelfIntent.ASSISTANT_HELP: HELP_100,
    SelfIntent.ASSISTANT_MEMORY: MEMORY_100,
    SelfIntent.ASSISTANT_LANGUAGE: LANGUAGE_100,
    SelfIntent.ASSISTANT_OFFLINE: OFFLINE_100,
    SelfIntent.ASSISTANT_TECHNOLOGY: TECHNOLOGY_100,
}

GENERIC_FALLBACK_MARKERS = (
    "reliable verified jaankari",
    "reliable verified information",
    "thoda context chahiye",
)


def _confidence_ok(result) -> bool:
    return result.intent != SelfIntent.UNKNOWN and result.confidence >= 0.60


@pytest.mark.parametrize("intent,utterances", list(DATASET.items()), ids=lambda x: x.value if isinstance(x, SelfIntent) else "")
def test_dataset_size_is_100(intent, utterances):
    assert len(utterances) == 100, f"{intent.value} has {len(utterances)}, expected 100"


@pytest.mark.parametrize("intent,utterances", list(DATASET.items()), ids=lambda x: x.value if isinstance(x, SelfIntent) else "")
def test_paraphrases_map_to_intent(intent, utterances):
    failures = []
    for u in utterances:
        r = detect_self_intent(u)
        if r.intent != intent:
            failures.append((u, r.intent.value, round(r.confidence, 2)))
    assert not failures, f"{intent.value} failures ({len(failures)}): {failures[:12]}"


def test_accuracy_report_by_intent(capsys):
    total_ok = total = 0
    lines = []
    all_failures = []
    for intent, utterances in DATASET.items():
        ok = 0
        for u in utterances:
            r = detect_self_intent(u)
            total += 1
            if r.intent == intent and r.confidence >= 0.60:
                ok += 1
                total_ok += 1
            else:
                all_failures.append((intent.value, u, r.intent.value, round(r.confidence, 2)))
        lines.append(f"{intent.value}: {ok}/{len(utterances)} = {ok / len(utterances):.1%}")
    with capsys.disabled():
        print("\n==== SELF-INTENT ACCURACY ====")
        for line in lines:
            print(line)
        print(f"TOTAL: {total_ok}/{total} = {total_ok / total:.1%}")
        if all_failures:
            print("FAILED UTTERANCES:")
            for f in all_failures:
                print(f"  {f}")
    assert total_ok == total, f"{len(all_failures)} utterances failed: {all_failures[:12]}"


# ---------------------------------------------------------------------------
# Spec section 18: acceptance test (exact lists from the requirement)
# ---------------------------------------------------------------------------

ACCEPT_IDENTITY = [
    "aap ka naam kya hai?", "tumhara naam kya hai?", "what is your name?",
    "who are you?", "naam batao", "tum kaun ho?",
]
ACCEPT_CREATOR = [
    "tum ko kisne banaya?", "tumhe kisne banaya?", "who created you?",
    "who made you?", "who built you?", "who create you?", "tumhara creator kaun hai?",
]
ACCEPT_CAPABILITIES = [
    "tum kya kar sakte ho?", "what can you do?", "tumhare capabilities kya hain?",
    "what are you capable of?", "mere liye kya kar sakte ho?",
]


@pytest.mark.parametrize("u", ACCEPT_IDENTITY)
def test_acceptance_identity(u):
    r = detect_self_intent(u)
    assert r.intent == SelfIntent.ASSISTANT_IDENTITY, (u, r.intent, r.confidence)
    assert r.confidence >= 0.90, (u, r.confidence)


@pytest.mark.parametrize("u", ACCEPT_CREATOR)
def test_acceptance_creator(u):
    r = detect_self_intent(u)
    assert r.intent == SelfIntent.ASSISTANT_CREATOR_ORIGIN, (u, r.intent, r.confidence)
    assert r.confidence >= 0.90, (u, r.confidence)


@pytest.mark.parametrize("u", ACCEPT_CAPABILITIES)
def test_acceptance_capabilities(u):
    r = detect_self_intent(u)
    assert r.intent == SelfIntent.ASSISTANT_CAPABILITIES, (u, r.intent, r.confidence)
    assert r.confidence >= 0.90, (u, r.confidence)


# ---------------------------------------------------------------------------
# Normalization / typo / STT tolerance (spec sections 4, 11, 12)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected_norm_part", [
    ("who r u?", "who are you"),
    ("ur name?", "your naam"),
    ("wat is ur name", "what is your naam"),
    ("tumhara nam kya h", "tumhara naam kya hai"),
    ("tumko kisne bnaya", "tum ko kisne banaya"),
    ("tumhe kis ne banaya", "tumhe kis ne banaya"),
])
def test_normalization_preserves_original_and_normalizes(raw, expected_norm_part):
    r = detect_self_intent(raw)
    assert r.original_text == raw
    assert expected_norm_part in r.normalized_text, (r.normalized_text, expected_norm_part)


@pytest.mark.parametrize("u,intent", [
    ("tumhara nam kya h", SelfIntent.ASSISTANT_IDENTITY),
    ("tumara naam kya hai", SelfIntent.ASSISTANT_IDENTITY),
    ("tumko kisne bnaya", SelfIntent.ASSISTANT_CREATOR_ORIGIN),
    ("who creatd you", SelfIntent.ASSISTANT_CREATOR_ORIGIN),
    ("wat is ur name", SelfIntent.ASSISTANT_IDENTITY),
    ("who made u", SelfIntent.ASSISTANT_CREATOR_ORIGIN),
    ("tumhe kisne bnaya", SelfIntent.ASSISTANT_CREATOR_ORIGIN),
    ("who create you", SelfIntent.ASSISTANT_CREATOR_ORIGIN),
    ("tum ko kisne banaya", SelfIntent.ASSISTANT_CREATOR_ORIGIN),
    ("tumko kisne banaya", SelfIntent.ASSISTANT_CREATOR_ORIGIN),
])
def test_typo_and_stt_tolerance(u, intent):
    r = detect_self_intent(u)
    assert r.intent == intent, (u, r.intent, r.confidence, r.normalized_text)


# ---------------------------------------------------------------------------
# Entity + intent (spec section 13)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("u,intent", [
    ("JARVIS ko kisne banaya?", SelfIntent.ASSISTANT_CREATOR_ORIGIN),
    ("JARVIS kya kya kar sakta hai?", SelfIntent.ASSISTANT_CAPABILITIES),
    ("ye JARVIS kisne banaya?", SelfIntent.ASSISTANT_CREATOR_ORIGIN),
])
def test_entity_extraction_with_intent(u, intent):
    r = detect_self_intent(u)
    assert r.intent == intent, (u, r.intent)
    assert r.entities.get("assistant") == "JARVIS"


# ---------------------------------------------------------------------------
# Guards: never hijack user-profile or general-knowledge queries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("u", [
    "mera naam kya hai",
    "maine tumhe apna naam kya bataya tha",
    "meri hobby kya hai",
    "Computer kisne banaya tha?",
    "Bluetooth kisne banaya tha?",
    "Python kisne banaya tha?",
    "open chrome",
    "volume 50 karo",
    # Anti-hijack: generic "wala"/"chal raha" utterances belong to existing
    # reference-resolution and conversational flows, never to self-intents.
    "ye doosra wala hai",
    "doosre wale pe jao",
    "aur batao kya chal raha hai",
    "kya chal raha hai",
    "isko band karo",
    "Chrome kholo",
    "YouTube kholo",
    "ye kaun se browser mein hai?",
    "haan, is par click karo",
    "Rahul kahan likha hai?",
    "main lunch karne ja raha hoon",
    "main kha ke aaya",
    "system lock hai kya?",
    "kya tum chrome open kar sakte ho",
    "mere liye vlc open kar sakti ho",
    "wifi on karo",
    "tumhara AI model kya hai",
    "how to do port forwarding",
])
def test_guards_defer_to_existing_flows(u):
    r = detect_self_intent(u)
    assert r.intent == SelfIntent.UNKNOWN, (u, r.intent, r.confidence)


# ---------------------------------------------------------------------------
# Contextual follow-ups (spec section 7)
# ---------------------------------------------------------------------------

def test_context_resolves_bare_creator_followup():
    first = detect_self_intent("tumhara naam kya hai?")
    assert first.intent == SelfIntent.ASSISTANT_IDENTITY
    second = detect_self_intent("kisne banaya?", last_intent=first.intent.value)
    assert second.intent == SelfIntent.ASSISTANT_CREATOR_ORIGIN
    assert second.confidence >= 0.60


def test_context_resolves_capability_continuation():
    first = detect_self_intent("tum kya kar sakte ho?")
    assert first.intent == SelfIntent.ASSISTANT_CAPABILITIES
    second = detect_self_intent("aur?", last_intent=first.intent.value)
    assert second.intent == SelfIntent.ASSISTANT_CAPABILITIES


def test_bare_followup_without_context_resolves_to_self():
    # In a 1:1 assistant chat a bare "kisne banaya?" is self-directed.
    # (Queries with a real entity — "Computer kisne banaya?" — still defer.)
    r = detect_self_intent("kisne banaya?")
    assert r.intent == SelfIntent.ASSISTANT_CREATOR_ORIGIN, (r.intent, r.confidence)


# ---------------------------------------------------------------------------
# Response knowledge: no hallucination, no generic fallback (spec section 14)
# ---------------------------------------------------------------------------

def test_identity_response_is_self_knowledge():
    r = detect_self_intent("aap ka naam kya hai?")
    assert r.response_source == "SELF_KNOWLEDGE"
    assert "JARVIS" in (r.response_text or "")
    for marker in GENERIC_FALLBACK_MARKERS:
        assert marker not in (r.response_text or "")


def test_creator_response_does_not_hallucinate():
    r = detect_self_intent("tum ko kisne banaya?")
    assert r.response_text is not None
    assert "JARVIS project" in r.response_text
    assert "configured nahi hai" in r.response_text
    for marker in GENERIC_FALLBACK_MARKERS:
        assert marker not in r.response_text


def test_greeting_defers_to_existing_greeting_flow():
    r = detect_self_intent("hello")
    assert r.intent == SelfIntent.ASSISTANT_GREETING
    assert r.response_text is None  # existing greeting flow owns the reply


# ---------------------------------------------------------------------------
# End-to-end through the real pipeline (no generic fallback for acceptance set)
# ---------------------------------------------------------------------------

@pytest.fixture
def jarvis_core(tmp_path):
    from main import create_jarvis
    db_path = str(tmp_path / "self_intent.db").replace("\\", "/")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "system:\n  name: JARVIS\nmemory:\n  db_path: \"" + db_path + "\"\n"
        "brain:\n  llm_provider: mock\n  model: llama3\n"
        "plugins:\n  plugin_dir: plugins\n  auto_load: false\n",
        encoding="utf-8",
    )
    return create_jarvis(str(config_path))


@pytest.mark.parametrize("u", ACCEPT_IDENTITY + ACCEPT_CREATOR + ACCEPT_CAPABILITIES)
def test_end_to_end_no_generic_fallback(jarvis_core, u):
    resp = jarvis_core.process_input(u)
    for marker in GENERIC_FALLBACK_MARKERS:
        assert marker not in resp, (u, resp)
    assert resp.strip(), u


def test_end_to_end_context_followup(jarvis_core):
    first = jarvis_core.process_input("tumhara naam kya hai?")
    assert "JARVIS" in first
    second = jarvis_core.process_input("kisne banaya?")
    for marker in GENERIC_FALLBACK_MARKERS:
        assert marker not in second, second
    assert "creator" in second or "JARVIS project" in second, second
