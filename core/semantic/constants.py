# core/semantic/constants.py
"""Centralized lexical constants, verb patterns, keywords, and precompiled regexes for NLU."""

import re
from typing import Dict, List

PLAY_VERBS: List[str] = [
    r'\bplay\s+karo\b', r'\bplay\s+kar\b', r'\bplay\b',
    r'\bchalao\s+na\b', r'\bchala\s+na\b', r'\bchalao\b', r'\bchala\s+do\b', r'\bchala\b',
    r'\blaga\s+do\b', r'\blaga\s+de\b', r'\blaga\b',
    r'\bbajao\s+na\b', r'\bbajao\b', r'\bbaja\s+do\b', r'\bbaja\s+de\b', r'\bbaja\b',
    r'\bsunao\s+na\b', r'\bsunao\b', r'\bsuna\s+do\b', r'\bsuna\s+de\b', r'\bsuna\b',
    r'\bstream\b', r'\bstart\b'
]

OPEN_VERBS: List[str] = [
    r'\bkhol\s+do\b', r'\bkhol\s+de\b', r'\bkholiye\b', r'\bkholo\b',
    r'\bopen\s+karo\b', r'\bopen\s+kar\s+do\b', r'\bopen\s+kijiye\b', r'\bopen\b',
    r'\blaunch\s+karo\b', r'\blaunch\s+kar\s+do\b', r'\blaunch\b',
    r'\bstart\s+karo\b', r'\bstart\s+kar\s+do\b', r'\bstart\b',
    r'\bchalao\b', r'\bchala\s+do\b', r'\bchala\s+de\b',
    r'\bchalu\s+karo\b', r'\bchalu\s+kar\s+do\b',
    r'\brun\s+karo\b', r'\brun\b'
]

SEARCH_VERBS: List[str] = [
    r'\bsearch\s+karo\b', r'\bsearch\s+kar\s+do\b', r'\bsearch\s+kar\b',
    r'\bsearch\b', r'\bdhoondo\b', r'\bdhoond\s+do\b', r'\bdhoondiye\b',
    r'\bfind\b'
]

SERVICE_PATTERNS: Dict[str, List[str]] = {
    "youtube": [
        r'\b(?:youtube|youtub|youtubee|utube)\s+(?:pe|par|me|mein|par\s+bhi|ke\s+upar)\b',
        r'\bon\s+(?:youtube|youtub|youtubee|utube)\b', r'\bin\s+(?:youtube|youtub|youtubee|utube)\b',
        r'\byt\s+(?:pe|par|me|mein)\b',
        r'\b(?:youtube|youtub|youtubee|utube)\b', r'\byt\b'
    ],
    "vlc": [
        r'\bvlc\s+(?:pe|par|me|mein|player\s+me)\b',
        r'\bon\s+vlc\b', r'\bin\s+vlc\b',
        r'\bvlc\b'
    ],
    "browser": [
        r'\b(?:browser|chrome|chrom|crome|brave|firefox|edge)\s+(?:pe|par|me|mein)\b',
        r'\bin\s+(?:browser|chrome|chrom|crome|brave)\b',
        r'\bon\s+(?:browser|chrome|chrom|crome|brave)\b'
    ]
}


WINDOW_OPERATIONS: Dict[str, List[str]] = {
    "maximize": [
        r'\b(?:maximi[sz]e|fullscreen|full\s+screen|bada\s+karo|badi\s+karo|bada|badi)(?:\s+(?:karo|kar\s+do|kar|do|kijiye))?\b',
        r'\bmaximi[sz]e\s+window\b', r'\bwindow\s+maximi[sz]e\b'
    ],
    "minimize": [
        r'\b(?:minimi[sz]e|chhota\s+karo|chhoti\s+karo|chhota|chhoti)(?:\s+(?:karo|kar\s+do|kar|do|kijiye))?\b',
        r'\bminimi[sz]e\s+window\b', r'\bwindow\s+minimi[sz]e\b'
    ],
    "restore": [
        r'\b(?:restore|unmaximize)(?:\s+(?:karo|kar\s+do|kar|do|kijiye))?\b',
        r'\brestore\s+window\b', r'\bwindow\s+restore\b'
    ],
    "focus": [
        r'\b(?:focus|bring\s+to\s+front|foreground|foreground\s+me|foreground\s+mein|samne\s+lao|saamne\s+lao|switch\s+to)(?:\s+(?:karo|kar\s+do|kar|do|kijiye|lao))?\b',
        r'\bfocus\s+on\b', r'\bopen\s+in\s+foreground\b', r'\bfocus\s+karo\b'
    ],
    "close": [
        r'\b(?:close|band\s+karo|band\s+kar\s+do|band\s+kar|kill|terminate|exit)(?:\s+(?:karo|kar\s+do|kar|do|kijiye))?\b',
        r'\bclose\s+window\b', r'\bwindow\s+close\b'
    ],
    "move": [
        r'\b(?:move|shift)(?:\s+(?:karo|kar\s+do|kar|do|kijiye))?\b', r'\bmove\s+window\b'
    ],
    "resize": [
        r'\b(?:resize)(?:\s+(?:karo|kar\s+do|kar|do|kijiye))?\b', r'\bresize\s+window\b'
    ]
}

POSITION_KEYWORDS: Dict[str, List[str]] = {
    "top_left": [
        r'\b(?:top\s+left|left\s+top|upar\s+baayein|upar\s+baaye|left\s+top\s+corner|top\s+left\s+corner)\b'
    ],
    "top_right": [
        r'\b(?:top\s+right|right\s+top|upar\s+daayein|upar\s+daaye|right\s+top\s+corner|top\s+right\s+corner)\b'
    ],
    "bottom_left": [
        r'\b(?:bottom\s+left|left\s+bottom|neeche\s+baayein|neeche\s+baaye|left\s+bottom\s+corner|bottom\s+left\s+corner)\b'
    ],
    "bottom_right": [
        r'\b(?:bottom\s+right|right\s+bottom|neeche\s+daayein|neeche\s+daaye|right\s+bottom\s+corner|bottom\s+right\s+corner)\b'
    ],
    "left": [
        r'\b(?:left\s+side|left\s+mein|left\s+me|left\s+par|left\s+pe|left|baayein|baaye)\b'
    ],
    "right": [
        r'\b(?:right\s+side|right\s+mein|right\s+me|right\s+par|right\s+pe|right|daayein|daaye)\b'
    ],
    "top": [
        r'\b(?:top\s+side|top\s+mein|top\s+me|top\s+par|top\s+pe|top|upar)\b'
    ],
    "bottom": [
        r'\b(?:bottom\s+side|bottom\s+mein|bottom\s+me|bottom\s+par|bottom\s+pe|bottom|neeche)\b'
    ],
    "center": [
        r'\b(?:center\s+mein|center\s+me|center|beech\s+mein|beech\s+me|middle)\b'
    ]
}

KNOWN_APPS: List[str] = [
    "microsoft power point", "microsoft powerpoint", "ms power point", "ms powerpoint",
    "power point", "powerpoint", "powerpnt", "ppt",
    "microsoft excel", "ms excel", "msexcel", "excel",
    "microsoft word", "ms word", "winword", "msword", "word",
    "microsoft access", "ms access", "msaccess", "access",
    "microsoft publisher", "ms publisher", "mspub", "publisher",
    "chrome", "google chrome", "brave", "vlc", "notepad", "calculator", "calc",
    "code", "vscode", "vs code", "spotify", "firefox", "edge", "microsoft edge",
    "browser", "youtube", "settings", "setting", "windows settings", "system settings",
    "control panel", "task manager", "taskmgr", "camera", "paint", "whatsapp",
    "terminal", "cmd", "explorer", "file explorer", "store", "microsoft store",
    "windows store", "ms store", "msstore", "discord", "telegram", "photos",
    "snipping tool", "clock", "weather", "maps"
]

# Precompiled regex patterns for high-frequency matching
COMPILED_PLAY_VERBS = [re.compile(p, flags=re.IGNORECASE) for p in PLAY_VERBS]
COMPILED_OPEN_VERBS = [re.compile(p, flags=re.IGNORECASE) for p in OPEN_VERBS]
COMPILED_SEARCH_VERBS = [re.compile(p, flags=re.IGNORECASE) for p in SEARCH_VERBS]

COMPILED_WINDOW_OPS = {
    op: [re.compile(p, flags=re.IGNORECASE) for p in patterns]
    for op, patterns in WINDOW_OPERATIONS.items()
}

COMPILED_POSITIONS = {
    pos: [re.compile(p, flags=re.IGNORECASE) for p in patterns]
    for pos, patterns in POSITION_KEYWORDS.items()
}
