# core/knowledge/news/formatter.py
"""
Response formatter for the Live News Engine.
Generates structured text for GUI/chatbox display and natural conversational speech for TTS.
"""

from typing import List, Tuple

from .models import NewsCategory, NewsItem


class NewsResponseFormatter:
    """Formats news headlines into visual and spoken responses."""

    CATEGORY_LABELS_HI = {
        NewsCategory.TOP: "mukhya",
        NewsCategory.WORLD: "duniya ki",
        NewsCategory.INDIA: "desh ki",
        NewsCategory.TECHNOLOGY: "technology",
        NewsCategory.BUSINESS: "business aur bazaar ki",
        NewsCategory.SPORTS: "sports aur khel ki",
        NewsCategory.ENTERTAINMENT: "entertainment",
        NewsCategory.SCIENCE: "science aur vigyan ki",
    }

    CATEGORY_LABELS_EN = {
        NewsCategory.TOP: "top",
        NewsCategory.WORLD: "world",
        NewsCategory.INDIA: "national",
        NewsCategory.TECHNOLOGY: "technology",
        NewsCategory.BUSINESS: "business",
        NewsCategory.SPORTS: "sports",
        NewsCategory.ENTERTAINMENT: "entertainment",
        NewsCategory.SCIENCE: "science",
    }

    ORDINAL_PREFIXES_HI = ["Pehli", "Doosri", "Teesri", "Chauthi", "Paanchvi"]
    ORDINAL_PREFIXES_EN = ["First", "Second", "Third", "Fourth", "Fifth"]

    @classmethod
    def format_news(
        cls,
        headlines: List[NewsItem],
        category: NewsCategory = NewsCategory.TOP,
        is_hindi: bool = True,
        search_topic: str = "",
        is_stale_fallback: bool = False
    ) -> Tuple[str, str]:
        """
        Formats headlines into (formatted_display_text, spoken_tts_text).
        """
        if not headlines:
            if is_hindi:
                msg = f"Maaf kijiye Boss, {search_topic or 'is topic'} par abhi koi live news nahi mili."
            else:
                msg = f"Sorry Boss, I couldn't find any live news on {search_topic or 'that topic'} right now."
            return msg, msg

        # Visual display formatting (numbered list with source attribution)
        display_lines: List[str] = []
        if is_stale_fallback:
            if is_hindi:
                header = "⚠️ **Boss, live feed refresh nahi ho paayi, lekin pichhli saved headlines ye hain:**\n"
            else:
                header = "⚠️ **Boss, live feed could not be refreshed right now; showing previously retrieved headlines:**\n"
        elif is_hindi:
            cat_str = cls.CATEGORY_LABELS_HI.get(category, "mukhya")
            if search_topic:
                header = f"📰 **Boss, '{search_topic}' se judi live news headlines:**\n"
            else:
                header = f"📰 **Boss, abhi ki {cat_str} live news headlines:**\n"
        else:
            cat_str = cls.CATEGORY_LABELS_EN.get(category, "top")
            if search_topic:
                header = f"📰 **Here are the latest news headlines on '{search_topic}', Boss:**\n"
            else:
                header = f"📰 **Here are the latest {cat_str} news headlines, Boss:**\n"

        display_lines.append(header)
        for i, item in enumerate(headlines, start=1):
            clean_t = item.clean_title()
            src = f" — *{item.source}*" if item.source else ""
            display_lines.append(f"{i}. {clean_t}{src}")

        formatted_text = "\n".join(display_lines)

        # Natural conversational spoken flow for TTS (first 3 headlines)
        speech_parts: List[str] = []
        speech_limit = min(3, len(headlines))

        if is_stale_fallback:
            if is_hindi:
                speech_intro = "Boss, live feed update nahi mil paayi, pichhli saved headlines ye hain."
            else:
                speech_intro = "Boss, live news could not be refreshed right now; here are the previously retrieved headlines."
        elif is_hindi:
            speech_intro = f"Boss, abhi ki {cls.CATEGORY_LABELS_HI.get(category, 'top')} headlines ye hain."
        else:
            speech_intro = f"Here are the top {cls.CATEGORY_LABELS_EN.get(category, 'news')} headlines, Boss."

        speech_parts.append(speech_intro)
        for i in range(speech_limit):
            clean_t = headlines[i].clean_title()
            if is_hindi:
                ord_prefix = cls.ORDINAL_PREFIXES_HI[i] if i < len(cls.ORDINAL_PREFIXES_HI) else f"Number {i+1}"
            else:
                ord_prefix = cls.ORDINAL_PREFIXES_EN[i] if i < len(cls.ORDINAL_PREFIXES_EN) else f"Number {i+1}"
            speech_parts.append(f"{ord_prefix}, {clean_t}.")

        spoken_text = " ".join(speech_parts)
        return formatted_text, spoken_text

    @classmethod
    def format_offline_error(cls, is_hindi: bool = True) -> Tuple[str, str]:
        """Formats network unreachable message."""
        if is_hindi:
            msg = "Internet connection uplabdh nahi hai, isliye abhi live news update nahi mil paayi, Boss."
        else:
            msg = "Internet connection is currently unavailable, so live news could not be retrieved, Boss."
        return msg, msg
