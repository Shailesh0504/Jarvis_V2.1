# gui/island/__init__.py
"""JARVIS Island — Coucou Windows Dynamic Island Architecture.

Full fidelity reproduction of the Coucou Windows Dynamic Island interaction model:
- Top-center floating dynamic island canvas (720x320)
- Hidden when idle (wake strip), compact pill (288x32), expanded card (640x160..240)
- Spring-based physics morphing with sub-stepped numerical integration
- Original futuristic JARVIS Character bot companion
- Unified card views: Overview, Approval, Question, Finished, Error, Chat, Drop
- DPI-aware and multi-monitor ready
"""

from .state_machine import IslandState, IslandStateMachine, GuiVisibilityState
from .visibility_manager import CoucouVisibilityManager
from .character import JarvisCharacter, is_affection_or_praise
from .pills import StatusPill, ToolPill, ActiveAppPill
from .activity_card import ActivityCard
from .confirmation_card import ConfirmationCard
from .question_card import QuestionCard
from .chat_view import IslandChatView
from .file_drop import FileDropTarget
from .controller import IslandController
from .animator import Spring, Tracked, IslandPhysicsAnimator
from .icons import create_coucou_icon
from .views import (
    CoucouHeaderWidget,
    CoucouOverviewCard,
    CoucouApprovalCard,
    CoucouQuestionCard,
    CoucouFinishedCard,
    CoucouErrorCard,
    CoucouChatCard,
    CoucouDropCard
)
from .island import CoucouIslandWidget

from .position_manager import AnchorPositionManager
from .accessories import Accessory, AccessoryManager
from .emotes import Emote, EMOTE_CONFIG, emote_from_string
from .floater import FloatStore, MochiFloater, FLOAT_SIZE
from .home_context import HomeStore, HomeKind, LONG_IDLE_SEC, describe_idle, resolve_time_greeting, resolve_context_greeting

__all__ = [
    "GuiVisibilityState",
    "CoucouVisibilityManager",
    "IslandState",
    "IslandStateMachine",
    "JarvisCharacter",
    "is_affection_or_praise",
    "StatusPill",
    "ToolPill",
    "ActiveAppPill",
    "ActivityCard",
    "ConfirmationCard",
    "QuestionCard",
    "IslandChatView",
    "FileDropTarget",
    "IslandController",
    "Spring",
    "Tracked",
    "IslandPhysicsAnimator",
    "create_coucou_icon",
    "CoucouHeaderWidget",
    "CoucouOverviewCard",
    "CoucouApprovalCard",
    "CoucouQuestionCard",
    "CoucouFinishedCard",
    "CoucouErrorCard",
    "CoucouChatCard",
    "CoucouDropCard",
    "CoucouIslandWidget",
    "AnchorPositionManager",
    "Accessory",
    "AccessoryManager",
    "Emote",
    "EMOTE_CONFIG",
    "emote_from_string",
    "FloatStore",
    "MochiFloater",
    "FLOAT_SIZE",
    "HomeStore",
    "HomeKind",
    "LONG_IDLE_SEC",
    "describe_idle",
    "resolve_time_greeting",
    "resolve_context_greeting",
]
