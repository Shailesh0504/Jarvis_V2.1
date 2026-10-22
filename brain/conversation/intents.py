# brain/conversation/intents.py
"""
Rich Conversational Intent Definitions for Jarvis V2.
Encapsulates human-like dialogue categories across Hindi, Hinglish, and English.
"""

from enum import Enum


class ConversationalIntent(str, Enum):
    """Exhaustive conversational intents for everyday dialogue."""

    # 1. Core Executable / Tool Command (diverts to Plugin Router)
    COMMAND = "COMMAND"

    # 2. Greetings & Salutations
    GREETING = "GREETING"
    FAREWELL = "FAREWELL"

    # 3. Status, Well-being & Small Talk
    HOW_ARE_YOU = "HOW_ARE_YOU"
    USER_STATE_UPDATE = "USER_STATE_UPDATE"
    ACTIVITY_UPDATE = "ACTIVITY_UPDATE"
    STATUS_CHECK = "STATUS_CHECK"
    LISTENING_CHECK = "LISTENING_CHECK"
    HELP_INQUIRY = "HELP_INQUIRY"

    # 4. Acknowledgements, Confirmations & Yes/No
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    CONFIRMATION_YES = "CONFIRMATION_YES"
    CONFIRMATION_NO = "CONFIRMATION_NO"

    # 5. Social Etiquette (Politeness)
    GRATITUDE = "GRATITUDE"
    APOLOGY = "APOLOGY"
    WELCOME_NO_PROBLEM = "WELCOME_NO_PROBLEM"

    # 6. Entertainment & Mood
    JOKE = "JOKE"
    STORY = "STORY"
    EMOTIONAL_MOOD = "EMOTIONAL_MOOD"

    # 7. Reasoning, Opinions & Advice
    OPINION_REQUEST = "OPINION_REQUEST"
    SUGGESTION_REQUEST = "SUGGESTION_REQUEST"
    EXPLANATION_REQUEST = "EXPLANATION_REQUEST"
    QUESTION_WH = "QUESTION_WH"

    # 8. Meta-Conversation & Control
    REPEAT_REQUEST = "REPEAT_REQUEST"
    DETAIL_REQUEST = "DETAIL_REQUEST"
    SUMMARY_REQUEST = "SUMMARY_REQUEST"
    CORRECTION = "CORRECTION"
    TOPIC_CHANGE = "TOPIC_CHANGE"
    DISMISSAL_CANCEL = "DISMISSAL_CANCEL"
    INTERRUPTION_WAIT = "INTERRUPTION_WAIT"
    FOLLOW_UP_CONTINUATION = "FOLLOW_UP_CONTINUATION"
    CONVERSATION_START = "CONVERSATION_START"
    UNCERTAINTY_CONFUSION = "UNCERTAINTY_CONFUSION"
    TIME_DATE_QUERY = "TIME_DATE_QUERY"

    # 9. Complaints & Feedback (e.g. listening behavior, performance criticism)
    USER_COMPLAINT_FEEDBACK = "USER_COMPLAINT_FEEDBACK"
    CRITICISM_LISTENING = "CRITICISM_LISTENING"
    COMPLAINT = "COMPLAINT"

    # 10. General Open Conversation Fallback
    GENERAL_CHAT = "GENERAL_CHAT"

    # Backward Compatibility Aliases
    CONVERSATION = "CONVERSATION"
    CONTINUATION = "CONTINUATION"
    EMOTIONAL = "EMOTIONAL"
    INTERRUPTION = "INTERRUPTION"
    ADVICE_OR_OPINION = "ADVICE_OR_OPINION"
    JOKE_OR_FUN = "JOKE_OR_FUN"
    EXPLANATION = "EXPLANATION"


# Direct alias for backward compatibility with existing tests and imports
ConversationIntent = ConversationalIntent
