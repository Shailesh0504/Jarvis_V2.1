# brain/conversation/registry.py
"""
Conversational Intent Registry & Semantic Pattern Matcher.
Maintains a structured, extensible dataset of everyday Hindi, Hinglish, and English
conversational intents, example utterances, and similarity scoring.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from .intents import ConversationalIntent
from .normalizer import ConversationNormalizer

logger = logging.getLogger("jarvis.brain.conversation.registry")


@dataclass
class IntentPattern:
    """Represents a conversational intent category with its seed phrases and matchers."""
    intent: ConversationalIntent
    exact_phrases: Set[str] = field(default_factory=set)
    regex_patterns: List[str] = field(default_factory=list)
    keyword_triggers: List[str] = field(default_factory=list)
    example_utterances: List[str] = field(default_factory=list)
    priority: int = 10  # Higher priority matched first


@dataclass
class MatchResult:
    """Result of semantic intent evaluation."""
    intent: ConversationalIntent
    confidence: float
    matched_pattern: Optional[str] = None
    extracted_text: Optional[str] = None


class ConversationIntentRegistry:
    """
    Central Registry of all Conversational Intents.
    Designed for easy extension, zero-latency matching, and runtime learning.
    """

    def __init__(self):
        self._patterns: Dict[ConversationalIntent, IntentPattern] = {}
        self._custom_utterances: Dict[str, ConversationalIntent] = {}
        self._initialize_core_dataset()

    def register_custom_utterance(self, utterance: str, intent: ConversationalIntent) -> None:
        """Dynamically registers a new user-approved phrase without code change."""
        norm = ConversationNormalizer.clean(utterance)
        if norm:
            self._custom_utterances[norm] = intent
            logger.info(f"Registry: Registered new custom utterance '{norm}' for intent '{intent.value}'")

    def _add_intent(
        self,
        intent: ConversationalIntent,
        exact_phrases: List[str],
        regex_patterns: Optional[List[str]] = None,
        keyword_triggers: Optional[List[str]] = None,
        examples: Optional[List[str]] = None,
        priority: int = 10
    ) -> None:
        cleaned_exact = {ConversationNormalizer.clean(p) for p in exact_phrases if p}
        self._patterns[intent] = IntentPattern(
            intent=intent,
            exact_phrases=cleaned_exact,
            regex_patterns=regex_patterns or [],
            keyword_triggers=[k.lower().strip() for k in (keyword_triggers or [])],
            example_utterances=examples or exact_phrases,
            priority=priority
        )

    def _initialize_core_dataset(self) -> None:
        """Initializes the comprehensive Hindi/Hinglish/English conversational dataset."""

        # 1. Corrections (Priority 100)
        self._add_intent(
            ConversationalIntent.CORRECTION,
            exact_phrases=[
                "nahi mera matlab ye tha", "main doosri baat keh raha tha",
                "nahi wo nahi", "not that", "mera matlab tha", "galat samajh gaye",
                "i meant", "actually mera matlab", "nahi main ye bol raha tha",
                "mera kehne ka matlab tha", "nahi aisa nahi", "wrong interpretation"
            ],
            regex_patterns=[
                r'\b(?:nahi|no|not)\b.*?\b(?:mera\s+matlab|i\s+meant|kehne\s+ka\s+matlab)\b',
                r'\b(?:galat|wrong)\s+(?:samajh|hai|interpret)\b'
            ],
            priority=100
        )

        # 1b. Complaints & Feedback on Listening / Performance (Priority 95)
        self._add_intent(
            ConversationalIntent.USER_COMPLAINT_FEEDBACK,
            exact_phrases=[
                "pehle kyon nahi listen kar rahi thi",
                "pehle kyu nahi listen kar rahi thi",
                "pehle kyon nahi listen kar raha tha",
                "pehle kyu nahi sun rahi thi",
                "pehle kyon nahi sun raha tha",
                "kab se bol raha tha listen kar",
                "kab se bol raha tha sun le",
                "kab se bol raha hoon listen kar",
                "kab se bol raha tha sun nahi raha",
                "kab se bol raha hoon sun nahi rahe",
                "itni der se bol raha tha",
                "itni der se bol raha hoon response nahi diya",
                "sun kyon nahi raha tha",
                "sun kyu nahi rahi thi",
                "listen kyon nahi kar raha tha",
                "listen kyu nahi kar rahi thi",
                "why were you not listening",
                "why did not you listen",
                "why didn't you listen",
                "why did not you respond",
                "why didn't you respond",
                "why were you not responding",
                "listen karna nonsense",
                "sun le nonsense",
                "response kyu nahi diya",
                "meri awaz nahi aa rahi kya",
                "sunai nahi de raha kya",
                "kya behri ho gayi ho",
                "kya behre ho gaye ho",
                "itni der se awaz de raha hoon",
                "sun nahi raha tha nonsense",
                "bakwaas sun nahi raha",
                "sun kyu nahi raha"
            ],
            regex_patterns=[
                r'\b(?:pehle|kab\s+se|itni\s+der\s+se|tab\s+se)\b.*?\b(?:listen|sun|respond|awaz|awaaz|bol\s+raha|bol\s+rahi|response)\b',
                r'\b(?:kyon|kyu|why)\b.*?\b(?:nahi\s+sun|nahi\s+listen|respond\s+nahi|reply\s+nahi|pick\s+nahi|sun\s+nahi|listen\s+nahi|response\s+nahi)\b',
                r'\b(?:sun\s+nahi\s+rahi?|listen\s+nahi\s+kar\s+rahi?|awaz\s+nahi\s+aa\s+rahi|awaaz\s+nahi\s+aa\s+rahi|sunai\s+nahi\s+de\s+raha|response\s+nahi\s+de\s+rahe?)\b',
                r'\b(?:listen\s+kar|sun\s+le|sun\s+na)\b.*?\b(?:nonsense|pagal|bakwas|bakwaas|bewakoof|idiot)\b',
                r'\b(?:nonsense|pagal|bakwas|bakwaas|bewakoof|idiot)\b.*?\b(?:listen|sun|bol|awaz|awaaz)\b'
            ],
            priority=95
        )

        # 2. Interruption / Hold on (Priority 90)
        self._add_intent(
            ConversationalIntent.INTERRUPTION_WAIT,
            exact_phrases=[
                "ruk", "ruko", "ruk jao", "ek minute", "wait", "hold on",
                "thahar", "thoda ruko", "zara ruko", "ek second", "wait a minute",
                "just a second", "just a minute", "ruko zara", "pause", "ek min"
            ],
            regex_patterns=[
                r'^(?:ruk|ruko|ruk\s+jao|ek\s+minute|wait|hold\s+on|zara\s+ruko|ek\s+sec|ek\s+min)$',
                r'^(?:ruk|ruko|wait|hold\s+on)\b'
            ],
            priority=90
        )

        # 3. Dismissal / Cancel / Never mind (Priority 85)
        self._add_intent(
            ConversationalIntent.DISMISSAL_CANCEL,
            exact_phrases=[
                "bas rehne do", "chhod do", "rehne de", "leave it", "never mind",
                "jane do", "kuch mat karo", "drop it", "forget it", "rehne do",
                "baad me karenge", "cancel karo", "ab nahi chahiye"
            ],
            regex_patterns=[
                r'\b(?:rehne\s+do|rehne\s+de|chhod\s+do|chhod\s+de|leave\s+it|never\s+mind|jane\s+do|forget\s+it)\b'
            ],
            priority=85
        )

        # 4. Greetings
        self._add_intent(
            ConversationalIntent.GREETING,
            exact_phrases=[
                "hi", "hello", "hey", "hey jarvis", "hello jarvis", "hi jarvis",
                "good morning", "good afternoon", "good evening", "namaste", "namaskar",
                "shubh prabhat", "halo", "helo", "yo jarvis", "yo", "wassup", "what's up",
                "subah bakhair", "adaab", "satsriakal", "pranam"
            ],
            regex_patterns=[
                r'^(?:hi|hello|hey|yo|namaste|pranam|adaab)(?:\s+jarvis)?$',
                r'^good\s+(?:morning|afternoon|evening)(?:\s+jarvis)?$'
            ],
            priority=70
        )

        # 5. Farewells
        self._add_intent(
            ConversationalIntent.FAREWELL,
            exact_phrases=[
                "bye", "good bye", "goodbye", "good night", "shubh ratri",
                "milte hain", "chalta hoon", "see you", "see you later", "catch you later",
                "take care", "fir milenge", "phir milte hain", "bye bye", "alvida",
                "main ja raha hoon", "ab main chalta hoon"
            ],
            regex_patterns=[
                r'\b(?:good\s+night|shubh\s+ratri|see\s+you|alvida|bye\s+bye)\b',
                r'^(?:bye|goodbye|chalta\s+hoon|milte\s+hain)$'
            ],
            priority=70
        )

        # 6. How are you & Status
        self._add_intent(
            ConversationalIntent.HOW_ARE_YOU,
            exact_phrases=[
                "kaise ho", "kya haal hai", "how are you", "kaisa chal raha hai",
                "sab theek hai", "sab theek", "how do you do", "sab kaisa hai",
                "kya chal raha hai", "how are things", "kya haal chaal", "sab badhiya"
            ],
            regex_patterns=[
                r'\b(?:kaise\s+ho|kya\s+haal|how\s+are\s+you|kaisa\s+chal\s+raha|sab\s+theek\s+hai)\b'
            ],
            priority=65
        )

        # 7. User State Updates (e.g. "Main theek hoon", "All good")
        self._add_intent(
            ConversationalIntent.USER_STATE_UPDATE,
            exact_phrases=[
                "main theek hoon", "main badhiya hoon", "all good", "i am good", "i am fine",
                "sab sahi hai", "badhiya", "ekdum first class", "mast hoon", "main bhi theek hoon",
                "sab badhiya chal raha hai", "everything is fine", "doing well"
            ],
            regex_patterns=[
                r'\b(?:main\s+(?:bhi\s+)?(?:theek|badhiya|mast|sahi|fine)\s+hoon|i\s+am\s+(?:fine|good|well|okay))\b',
                r'^(?:all\s+good|badhiya|mast|first\s+class)$'
            ],
            priority=60
        )

        # 8. Activity Updates (e.g. "Main khana khane ja raha hoon", "Office nikal raha hoon")
        self._add_intent(
            ConversationalIntent.ACTIVITY_UPDATE,
            exact_phrases=[
                "main abhi khana khane ja raha hoon", "khana khane ja raha hoon",
                "main jakar khata hun", "main office ja raha hoon", "main sone ja raha hoon",
                "main nahane ja raha hoon", "main padhai karne ja raha hoon", "walk pe ja raha hoon",
                "thoda kaam kar raha hoon", "main dinner kar raha hoon", "lunch karne ja raha hoon",
                "chalo khana kha kar aata hun", "main kal office jaunga"
            ],
            regex_patterns=[
                r'\b(?:main\s+)?(?:abhi\s+)?(?:khana\s+khane|office|sone|nahane|walk\s+pe|lunch|dinner|market)\s+(?:ja\s+raha|nikal\s+raha|kar\s+raha)\b',
                r'\b(?:khana\s+kha\s+kar|office\s+se\s+aakar)\b',
                r'\bmain\s+(?:jakar\s+khata|kal\s+office\s+jaunga|so\s+raha\s+hoon)\b'
            ],
            priority=75
        )

        # 9. Status Check ("Kya kar rahe ho?")
        self._add_intent(
            ConversationalIntent.STATUS_CHECK,
            exact_phrases=[
                "kya kar rahe ho", "kya kar raha hai", "what are you doing",
                "what's going on", "kya chal raha hai", "kya ho raha hai",
                "kya bana rahe ho", "kya soch rahe ho"
            ],
            regex_patterns=[
                r'(?<!time\s)(?<!samay\s)\b(?:kya\s+kar\s+rahe\s+ho|kya\s+kar\s+raha\s+hai|(?:abhi\s+)?kya\s+ho\s+raha\s+hai|what\s+are\s+you\s+doing)\b'
            ],
            priority=60
        )

        # 10. Listening Check ("Kya tum meri baat sun rahe ho?")
        self._add_intent(
            ConversationalIntent.LISTENING_CHECK,
            exact_phrases=[
                "kya tum meri baat sun rahe ho", "meri awaaz sun rahe ho", "kya meri awaaz aa rahi hai",
                "are you listening", "can you hear me", "sun rahe ho na", "kya tum sun rahe ho",
                "sun rahe ho jarvis", "kya tum active ho", "are you there"
            ],
            regex_patterns=[
                r'\b(?:meri\s+(?:baat|awaaz)\s+sun\s+rahe\s+ho|are\s+you\s+listening|can\s+you\s+hear\s+me|sun\s+rahe\s+ho)\b'
            ],
            priority=75
        )

        # 11. Help Inquiries ("Kya tum meri help kar sakte ho?")
        self._add_intent(
            ConversationalIntent.HELP_INQUIRY,
            exact_phrases=[
                "kya tum meri help kar sakte ho", "can you help me", "help chahiye",
                "kya tum meri madad karoge", "meri help karo", "need some help",
                "kya tum meri madad kar sakte ho", "help me out"
            ],
            regex_patterns=[
                r'\b(?:help\s+kar\s+sakte\s+ho|can\s+you\s+help|madad\s+kar\s+sakte\s+ho|help\s+chahiye)\b'
            ],
            priority=65
        )

        # 12. Acknowledgements
        self._add_intent(
            ConversationalIntent.ACKNOWLEDGEMENT,
            exact_phrases=[
                "achha", "theek hai", "okay", "ok", "samajh gaya", "chalo theek hai",
                "got it", "understood", "sahi hai", "theek", "thik", "accha theek hai",
                "hmm", "hmmm", "achha theek", "sahi baat hai", "i see"
            ],
            regex_patterns=[
                r'^(?:achha|theek\s+hai|okay|ok|samajh\s+gaya|chalo\s+theek\s+hai|got\s+it|understood|sahi\s+hai|hmm|hmmm)$'
            ],
            priority=50
        )

        # 13. Confirmations (Yes / No)
        self._add_intent(
            ConversationalIntent.CONFIRMATION_YES,
            exact_phrases=[
                "haan", "yes", "bilkul", "sahi bola", "haan wahi", "yeah", "sure",
                "zaroor", "exactly", "haan ji", "sahi", "haan karo", "ha"
            ],
            regex_patterns=[
                r'^(?:haan|yes|bilkul|yeah|sure|zaroor|exactly|haan\s+wahi|haan\s+ji)$'
            ],
            priority=55
        )

        self._add_intent(
            ConversationalIntent.CONFIRMATION_NO,
            exact_phrases=[
                "nahi", "no", "bilkul nahi", "nope", "na", "nahi chahiye",
                "nahi rehne do", "not now", "abhi nahi", "nahi mat karo"
            ],
            regex_patterns=[
                r'^(?:nahi|no|bilkul\s+nahi|nope|na|nahi\s+chahiye|not\s+now)$'
            ],
            priority=55
        )

        # 14. Gratitude
        self._add_intent(
            ConversationalIntent.GRATITUDE,
            exact_phrases=[
                "thanks", "thank you", "shukriya", "dhanyawad", "bahut shukriya",
                "thanks a lot", "thank you so much", "many thanks", "dhanyavad"
            ],
            regex_patterns=[
                r'\b(?:thanks|thank\s+you|shukriya|dhanyawad|dhanyavad)\b'
            ],
            priority=70
        )

        # 15. Apologies & Politeness
        self._add_intent(
            ConversationalIntent.APOLOGY,
            exact_phrases=[
                "sorry", "maaf karna", "my bad", "galti ho gayi", "so sorry",
                "maaf kijiye", "i am sorry", "pardon"
            ],
            regex_patterns=[
                r'\b(?:sorry|maaf\s+karna|my\s+bad|galti\s+ho\s+gayi|maaf\s+kijiye)\b'
            ],
            priority=70
        )

        self._add_intent(
            ConversationalIntent.WELCOME_NO_PROBLEM,
            exact_phrases=[
                "koi baat nahi", "no problem", "mention not", "you are welcome",
                "you're welcome", "welcome", "koi issue nahi", "chill hai"
            ],
            regex_patterns=[
                r'\b(?:koi\s+baat\s+nahi|no\s+problem|mention\s+not|you\s+are\s+welcome|welcome)\b'
            ],
            priority=65
        )

        # 16. Jokes & Storytelling
        self._add_intent(
            ConversationalIntent.JOKE,
            exact_phrases=[
                "joke suna", "koi funny joke suna", "chutkula", "hasao", "koi funny",
                "make me laugh", "koi mast joke", "ek joke sunao", "tell me a joke",
                "joke sunao", "koi chutkula sunao"
            ],
            regex_patterns=[
                r'\b(?:joke|chutkula|hasao|funny\s+joke|make\s+me\s+laugh)\b'
            ],
            priority=80
        )

        self._add_intent(
            ConversationalIntent.STORY,
            exact_phrases=[
                "kahani sunao", "story batao", "koi kahani", "tell a story",
                "tell me a story", "koi kissa sunao", "story sunao", "ek kahani sunao"
            ],
            regex_patterns=[
                r'\b(?:kahani\s+sunao|story\s+batao|tell\s+a\s+story|kissa\s+sunao|story\s+sunao)\b'
            ],
            priority=80
        )

        # 17. Emotional & Mood
        self._add_intent(
            ConversationalIntent.EMOTIONAL_MOOD,
            exact_phrases=[
                "mood kharab", "sad hoon", "bore ho raha", "gussa aa raha", "thak gaya",
                "dil nahi lag raha", "depressed", "khush hoon", "maja aa gaya", "stress hai",
                "tension hai", "mood off hai", "aaj bohot thak gaya", "feeling low"
            ],
            regex_patterns=[
                r'\b(?:mood\s+kharab|sad\s+hoon|bore\s+ho\s+raha|gussa\s+aa\s+raha|thak\s+gaya|depressed|stress|tension|feeling\s+low|mood\s+off)\b'
            ],
            priority=80
        )

        # 18. Opinions & Suggestions
        self._add_intent(
            ConversationalIntent.OPINION_REQUEST,
            exact_phrases=[
                "tumhare hisaab se kya better hai", "mujhe kya karna chahiye", "what do you think",
                "tumhara kya opinion hai", "kya suggestion hai", "kaunsa better hai",
                "what is your opinion", "which is better", "what do you suggest", "kya opinion hai"
            ],
            regex_patterns=[
                r'\b(?:tumhare\s+hisaab\s+se|kya\s+karna\s+chahiye|what\s+do\s+you\s+think|kya\s+opinion|kya\s+suggest|which\s+is\s+better)\b'
            ],
            priority=75
        )

        # 19. Explanations & Meanings
        self._add_intent(
            ConversationalIntent.EXPLANATION_REQUEST,
            exact_phrases=[
                "ye kaise kaam karta hai", "iska matlab kya hai", "explain karo", "how does this work",
                "mujhe samjhao", "iska kya arth hai", "what does this mean", "how it works",
                "mujhe explain karo", "achha tell me", "what is the meaning"
            ],
            regex_patterns=[
                r'\b(?:kaise\s+kaam\s+karta|iska\s+matlab\s+kya|explain\s+karo|how\s+does\s+(?:this|it)\s+work|samjhao)\b'
            ],
            priority=75
        )

        # 20. Wh-Questions / Follow-up Inquiry
        self._add_intent(
            ConversationalIntent.QUESTION_WH,
            exact_phrases=[
                "kyun", "kaise", "kab", "kahan", "kaun", "why", "how", "when", "where", "who",
                "kyun bhai", "kaise hoga", "kab hoga", "kahan hai", "kaun hai", "why so"
            ],
            regex_patterns=[
                r'^(?:kyun|kaise|kab|kahan|kaun|why|how|when|where|who)(?:\s+(?:bhai|yaar|hai|hoga))?$'
            ],
            priority=60
        )

        # 21. Repeat & Format Modifiers
        self._add_intent(
            ConversationalIntent.REPEAT_REQUEST,
            exact_phrases=[
                "dobara batao", "repeat karo", "firse bolo", "say again", "once more",
                "firse batao", "ek baar aur", "can you repeat"
            ],
            regex_patterns=[
                r'\b(?:dobara\s+batao|repeat\s+karo|firse\s+bolo|say\s+again|once\s+more|firse\s+batao)\b'
            ],
            priority=70
        )

        self._add_intent(
            ConversationalIntent.DETAIL_REQUEST,
            exact_phrases=[
                "detail mein samjhao", "explain in detail", "vistaar se batao",
                "thoda detail me", "in depth batao", "elaborate karo", "deep me samjhao"
            ],
            regex_patterns=[
                r'\b(?:detail\s+me|detail\s+mein|in\s+detail|vistaar\s+se|elaborate)\b'
            ],
            priority=70
        )

        self._add_intent(
            ConversationalIntent.SUMMARY_REQUEST,
            exact_phrases=[
                "short mein batao", "brief me batao", "summarize karo", "summary do",
                "chote me batao", "in short", "keep it short", "briefly batao"
            ],
            regex_patterns=[
                r'\b(?:short\s+me|short\s+mein|brief\s+me|brief\s+mein|summarize|summary|in\s+short)\b'
            ],
            priority=70
        )

        # 22. Topic Changes & Recall
        self._add_intent(
            ConversationalIntent.TOPIC_CHANGE,
            exact_phrases=[
                "topic change karo", "kuch aur baat karte hain", "let's talk about something else",
                "change the topic", "doosri baat karte hain", "kisi aur topic pe baat karo",
                "chalo kuch aur batao", "wapis usi baat par aao", "wapas usi baat par aao",
                "pehle wali baat par aao", "back to previous topic"
            ],
            regex_patterns=[
                r'\b(?:topic\s+change|kuch\s+aur\s+baat|something\s+else|doosri\s+baat|wapis\s+usi\s+baat|wapas\s+usi\s+baat|pehle\s+wali\s+baat)\b'
            ],
            priority=75
        )

        # 23. Continuity & Follow-ups
        self._add_intent(
            ConversationalIntent.FOLLOW_UP_CONTINUATION,
            exact_phrases=[
                "achha phir kya hua", "phir kya hua", "aur batao", "phir?", "fir?",
                "uske baad", "what next", "and then", "continue karo", "aage batao",
                "aur phir kya hua", "tell me more"
            ],
            regex_patterns=[
                r'\b(?:phir\s+kya\s+hua|uske\s+baad|aur\s+batao|what\s+next|and\s+then|aage\s+batao|tell\s+me\s+more)\b',
                r'^(?:phir|fir|aur\s+phir)$'
            ],
            priority=70
        )

        # 24. Conversation Starters
        self._add_intent(
            ConversationalIntent.CONVERSATION_START,
            exact_phrases=[
                "mujhe ek baat batao", "suno ek baat", "let me ask you something",
                "ek baat poochni thi", "ek sawal hai", "ek baat batao", "suno",
                "achha ek baat bata"
            ],
            regex_patterns=[
                r'\b(?:ek\s+baat\s+bata|suno\s+ek\s+baat|let\s+me\s+ask|ek\s+sawal\s+hai|ek\s+baat\s+poochni)\b'
            ],
            priority=70
        )

        # 25. Uncertainty & Confusion
        self._add_intent(
            ConversationalIntent.UNCERTAINTY_CONFUSION,
            exact_phrases=[
                "mujhe samajh nahi aaya", "confusing hai", "i don't understand",
                "pata nahi", "confused hoon", "kuch samajh nahi aa raha",
                "not clear", "samajh nahi pada"
            ],
            regex_patterns=[
                r'\b(?:samajh\s+nahi\s+(?:aaya|aa\s+raha|pada)|i\s+don\'?t\s+understand|confused\s+hoon|confusing\s+hai)\b'
            ],
            priority=70
        )

        # 26. Dynamic Time & Date Queries
        self._add_intent(
            ConversationalIntent.TIME_DATE_QUERY,
            exact_phrases=[
                "kitne baje hain", "kya time hua hai", "what time is it", "abhi kya time hai",
                "time kya hua hai", "time batao", "abhi kitne baje hain", "samay kya hai",
                "time kya ho raha hai", "kya time ho raha hai", "time kya hai", "time kya hua",
                "kitna time ho raha hai", "kitna time hua", "kitna baj raha hai", "kitne baj gaye",
                "aaj date kya hai", "what is the date today", "aaj ki tarikh kya hai",
                "aaj kaunsa din hai", "what day is today", "abhi subah hai ya dopahar",
                "abhi morning hai kya", "abhi afternoon hai kya", "abhi evening hai kya",
                "abhi raat hai kya", "current time kya hai", "aaj kya din hai"
            ],
            regex_patterns=[
                r'\b(?:kitne\s+baje|kya\s+time|what\s+time|time\s+kya|time\s+batao|time\s+bataiye|samay\s+kya|current\s+time|kitna\s+time|kitna\s+baj|kitne\s+baj)\b',
                r'\b(?:aaj\s+(?:ki\s+)?(?:date|tarikh)|what\s+(?:is\s+the\s+)?date|date\s+kya\s+hai)\b',
                r'\b(?:aaj\s+(?:kaun\s*sa|kya)\s+din|what\s+day\s+is\s+today)\b',
                r'\b(?:abhi\s+(?:morning|afternoon|evening|night|subah|dopahar|shaam|raat)\s+hai\s+kya|subah\s+hai\s+ya\s+dopahar)\b'
            ],
            priority=85
        )

    def match(self, text: str) -> MatchResult:
        """
        Evaluates input text against the intent registry with multi-tier matching:
        1. Custom learned user utterances (highest precedence)
        2. Exact phrase matches across all categories
        3. High-precision Regex patterns
        4. Token overlap and keyword similarity
        """
        normalized = ConversationNormalizer.clean(text)
        if not normalized:
            return MatchResult(intent=ConversationalIntent.GENERAL_CHAT, confidence=0.0)

        # 1. Custom runtime-registered phrases
        if normalized in self._custom_utterances:
            matched_int = self._custom_utterances[normalized]
            return MatchResult(intent=matched_int, confidence=1.0, matched_pattern=normalized)

        # Sort patterns by priority descending
        sorted_patterns = sorted(self._patterns.values(), key=lambda p: p.priority, reverse=True)

        # 2. Exact phrase matches
        for pat in sorted_patterns:
            if normalized in pat.exact_phrases:
                return MatchResult(intent=pat.intent, confidence=1.0, matched_pattern=normalized)

        # 3. Regex patterns
        for pat in sorted_patterns:
            if pat.intent == ConversationalIntent.LISTENING_CHECK:
                if any(v in normalized for v in ("screen", "window", "windows", "desktop", "display", "monitor", "dekh", "dikh")):
                    continue
            for reg in pat.regex_patterns:
                m = re.search(reg, normalized, re.IGNORECASE)
                if m:
                    return MatchResult(
                        intent=pat.intent,
                        confidence=0.95,
                        matched_pattern=reg,
                        extracted_text=m.group(0)
                    )

        # 4. Token Overlap & Semantic Proximity
        STOPWORDS = {
            "kya", "tum", "aap", "meri", "mera", "mere", "main", "hai", "hain", "ho",
            "ka", "ki", "ke", "ko", "se", "pe", "par", "me", "mein", "ye", "yeh", "wo",
            "woh", "the", "a", "an", "is", "are", "you", "my", "your", "to", "in", "on",
            "na", "toh", "aur", "and", "hun", "hoon", "tha", "thi"
        }
        input_tokens = set(normalized.split())
        best_intent = ConversationalIntent.GENERAL_CHAT
        best_score = 0.0
        best_match_str = None

        for pat in sorted_patterns:
            # Explicit guard: LISTENING_CHECK must not match visual/screen queries
            if pat.intent == ConversationalIntent.LISTENING_CHECK:
                if any(v in normalized for v in ("screen", "window", "windows", "desktop", "display", "monitor", "dekh", "dikh")):
                    continue
                if not any(a in normalized for a in ("sun", "awaaz", "hear", "listen", "audible", "baat")):
                    continue

            for ex in pat.example_utterances:
                ex_norm = ConversationNormalizer.clean(ex)
                ex_tokens = set(ex_norm.split())
                if not ex_tokens:
                    continue
                intersection = input_tokens.intersection(ex_tokens)
                if intersection:
                    # Require at least one non-stopword content token
                    content_tokens = intersection - STOPWORDS
                    if not content_tokens:
                        continue
                    score = len(intersection) / max(len(input_tokens), len(ex_tokens))
                    # Check substring match only for multi-word phrases with substantial coverage
                    if len(ex_tokens) >= 2 and (ex_norm in normalized or normalized in ex_norm):
                        coverage = len(ex_tokens) / max(len(input_tokens), 1)
                        if coverage >= 0.5:
                            score = max(score, 0.85)
                    if score > best_score and score >= 0.5:
                        best_score = score
                        best_intent = pat.intent
                        best_match_str = ex_norm

        if best_score >= 0.5:
            return MatchResult(intent=best_intent, confidence=round(best_score, 2), matched_pattern=best_match_str)

        return MatchResult(intent=ConversationalIntent.GENERAL_CHAT, confidence=0.3)

