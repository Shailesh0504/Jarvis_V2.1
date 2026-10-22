from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Dict, List, Optional
import uuid


class TurnOutcomeStatus(str, Enum):
    """Authoritative outcome status of an execution turn."""
    VERIFIED = "VERIFIED"       # Action observed & confirmed in physical system state
    UNVERIFIED = "UNVERIFIED"   # Action reported success at API level without confirmed physical state change
    FAILED = "FAILED"           # Action or verification failed
    AMBIGUOUS = "AMBIGUOUS"     # Disambiguation / clarification / candidate selection required


@dataclass
class TurnOutcome:
    """
    Minimal representation of the definitive execution outcome for a single turn.
    Free of GUI state, raw audio, or deep conversation history.
    """
    turn_id: str
    status: TurnOutcomeStatus
    execution_result: Optional[Any] = None       # core.execution.models.ExecutionResult
    verification_result: Optional[Any] = None    # core.execution.models.VerificationResult
    error: Optional[str] = None
    diagnostics: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "status": self.status.value if isinstance(self.status, TurnOutcomeStatus) else str(self.status),
            "execution_result": self.execution_result.to_dict() if hasattr(self.execution_result, "to_dict") else None,
            "verification_result": self.verification_result.to_dict() if hasattr(self.verification_result, "to_dict") else None,
            "error": self.error,
            "diagnostics": list(self.diagnostics),
            "timestamp": self.timestamp,
        }


@dataclass
class TurnContext:
    """Represents the context of a single user turn/interaction."""
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    raw_input: str = ""
    repaired_input: str = ""
    normalized_input: str = ""
    wake_word_detected: bool = False
    source: str = "cli"  # cli, voice, gui, api
    timestamp: float = field(default_factory=time.time)
    intent: Optional[Any] = None
    plan: Optional[Any] = None
    execution_results: List[Any] = field(default_factory=list)
    execution_outcome: Optional[TurnOutcome] = None
    response_text: str = ""
    status: str = "COMPLETED"  # "ACTIVE", "COMPLETED", "INTERRUPTED", "CANCELLED"
    generation_id: int = 0
    interrupted_at: Optional[float] = None
    active_question: Optional[str] = None
    pending_goal: Optional[str] = None
    missing_slots: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0


@dataclass
class UserContext:
    """Context information about the user."""
    user_id: str = "default_user"
    user_name: str = "Shailesh"
    role: str = "ADMIN"
    preferences: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SessionContext:
    """Manages active conversation session state and history buffer."""

    def __init__(self, session_id: Optional[str] = None, user: Optional[UserContext] = None):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.start_time: float = time.time()
        self.user: UserContext = user or UserContext()
        self.turns: List[TurnContext] = []
        self.active_variables: Dict[str, Any] = {}
        self.active_task_id: Optional[str] = None
        self.last_interaction_time: float = self.start_time

    def start_new_turn(self, raw_input: str, source: str = "cli") -> TurnContext:
        turn = TurnContext(raw_input=raw_input, source=source)
        if self.active_task_id:
            turn.metadata["active_task_id"] = self.active_task_id
        self.turns.append(turn)
        self.last_interaction_time = time.time()
        return turn

    def get_current_turn(self) -> Optional[TurnContext]:
        return self.turns[-1] if self.turns else None

    def get_recent_history(self, limit: int = 5) -> List[Dict[str, str]]:
        """Returns recent turns formatted for prompt/context injection."""
        history = []
        for turn in self.turns[-limit:]:
            if turn.raw_input:
                history.append({"role": "user", "content": turn.raw_input})
            if turn.response_text:
                history.append({"role": "assistant", "content": turn.response_text})
        return history

    def set_variable(self, key: str, value: Any) -> None:
        self.active_variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        return self.active_variables.get(key, default)

    def clear(self) -> None:
        self.turns.clear()
        self.active_variables.clear()
        self.active_task_id = None


@dataclass
class ActiveTargetContext:
    """
    Persistent active application, browser, window, tab, website, and file context across conversational turns.
    """
    target_type: str = "none"  # "website", "application", "window", "media", "document", "file"
    application: str = ""      # e.g. "browser", "brave", "chrome", "vlc", "excel"
    browser: str = ""          # e.g. "brave", "chrome", "edge", "firefox"
    window: str = ""           # Window title or hwnd string
    hwnd: int = 0
    tab: str = ""              # Active tab title or tab_id
    website: str = ""          # Canonical site name, e.g. "flipkart", "amazon", "youtube", "google"
    domain: str = ""           # Domain, e.g. "flipkart.com", "amazon.in", "youtube.com"
    page_title: str = ""       # Title of the page
    url: str = ""              # Current URL, e.g. "https://www.flipkart.com/"
    last_file: str = ""        # e.g. "monthly_sales.csv"
    last_file_path: str = ""   # e.g. "C:/.../monthly_sales.csv"
    last_entity: str = ""      # e.g. "sales", "inception", "shoes"
    last_action: str = ""      # e.g. "open_website", "search_products", "play_video", "open_file"
    last_search_query: str = ""  # e.g. "shoes"
    last_media_title: str = ""   # e.g. "Kesariya song", "Python tutorial"
    last_media_source: str = ""  # e.g. "youtube", "vlc"
    last_news_headlines: List[Any] = field(default_factory=list)
    last_intent: Optional[str] = None
    last_entities: Dict[str, Any] = field(default_factory=dict)
    last_service: str = ""
    last_raw_command: str = ""
    last_success: bool = True
    current_workflow: str = "" # e.g. "EXCEL_OPEN", "MEDIA_PLAY"
    active_workflow: Dict[str, Any] = field(default_factory=dict)
    pending_goal: Optional[str] = None
    missing_slots: List[str] = field(default_factory=list)
    filled_slots: Dict[str, Any] = field(default_factory=dict)
    active_task_id: Optional[str] = None
    active_task_goal: str = ""
    recent_candidates: List[Dict[str, Any]] = field(default_factory=list)
    relevant_entities: Dict[str, Any] = field(default_factory=dict)
    activity_history: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)
    ttl_seconds: float = 120.0

    @property
    def is_active(self) -> bool:
        if self.is_expired:
            return False
        return bool(self.website or self.application or self.url or self.last_file or self.last_intent)

    @property
    def last_application(self) -> str:
        return self.application

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.updated_at) > self.ttl_seconds

    def record_execution(
        self,
        action: str,
        target: str = "",
        application: str = "",
        file_path: str = "",
        entity: str = "",
        workflow: str = "",
    ) -> None:
        """Updates contextual memory after a successful execution (Rule 10)."""
        self.last_action = action
        if application:
            self.application = application.lower().strip()
        if file_path:
            import os
            self.last_file_path = file_path
            self.last_file = os.path.basename(file_path)
            self.target_type = "file"
        if entity:
            self.last_entity = entity
        if workflow:
            self.current_workflow = workflow
        if target and not file_path:
            self.relevant_entities["target"] = target
        self.updated_at = time.time()

    def set_website(self, site: str, url: str = "", domain: str = "", browser: str = "browser", action: str = "open_website", container: str = "") -> None:
        effective_browser = container or browser or "browser"
        self.target_type = "website"
        self.website = site.lower().strip()
        self.url = url
        self.domain = domain or (site.lower().strip() + ".com")
        self.application = effective_browser
        self.browser = effective_browser
        self.last_action = action
        self.page_title = f"{self.website.capitalize()}"
        self.relevant_entities.clear()
        self.updated_at = time.time()

    def set_application(self, app_name: str, hwnd: int = 0, title: str = "", action: str = "open_app") -> None:
        self.target_type = "application"
        self.application = app_name.lower().strip()
        self.hwnd = hwnd
        self.window = title
        self.page_title = title
        self.website = ""
        self.domain = ""
        self.url = ""
        self.last_action = action
        self.relevant_entities.clear()
        self.updated_at = time.time()

    def update_command_context(
        self,
        intent: str,
        action: str,
        entities: Optional[Dict[str, Any]] = None,
        success: bool = True,
        raw_command: str = "",
        service: str = "",
    ) -> None:
        """Updates authoritative short-term command context for natural language follow-up understanding."""
        self.last_intent = intent
        self.last_action = action
        self.last_entities = dict(entities or {})
        self.last_success = success
        self.last_raw_command = raw_command
        self.last_service = service
        self.updated_at = time.time()

    def get_command_context(self) -> Dict[str, Any]:
        """Returns short-term command context dictionary."""
        return {
            "last_intent": self.last_intent,
            "last_entities": self.last_entities,
            "last_action": self.last_action,
            "last_success": self.last_success,
            "last_service": self.last_service,
            "last_raw_command": self.last_raw_command,
        }

    def clear(self) -> None:
        self.target_type = "none"
        self.application = ""
        self.browser = ""
        self.window = ""
        self.hwnd = 0
        self.tab = ""
        self.website = ""
        self.domain = ""
        self.page_title = ""
        self.url = ""
        self.last_file = ""
        self.last_file_path = ""
        self.last_entity = ""
        self.last_action = ""
        self.last_search_query = ""
        self.last_intent = None
        self.last_entities.clear()
        self.last_service = ""
        self.last_raw_command = ""
        self.last_success = True
        self.current_workflow = ""
        self.recent_candidates.clear()
        self.relevant_entities.clear()
        self.updated_at = time.time()

    def record_media(self, title: str, source: str = "youtube", url: str = "") -> None:
        """Records played or searched video/song media."""
        if not title:
            return
        self.last_media_title = title.strip()
        self.last_media_source = source.strip().lower()
        if source.lower() == "youtube":
            self.website = "youtube"
            self.target_type = "website"
        elif source.lower() == "vlc":
            self.application = "vlc"
            self.target_type = "application"
        if url:
            self.url = url
        self.record_activity("media_playback", title=title, details=f"Played on {source}", source=source)
        self.updated_at = time.time()

    def record_activity(self, activity_type: str, title: str, details: str = "", source: str = "") -> None:
        """Appends an event to the short-term activity ring buffer."""
        record = {
            "type": activity_type,
            "title": title,
            "details": details,
            "source": source or self.get_context_key(),
            "timestamp": time.time(),
        }
        self.activity_history.append(record)
        if len(self.activity_history) > 20:
            self.activity_history.pop(0)

    def get_last_media(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent media playback record."""
        if self.last_media_title:
            return {
                "title": self.last_media_title,
                "source": self.last_media_source or "youtube",
                "timestamp": self.updated_at,
            }
        for act in reversed(self.activity_history):
            if act.get("type") == "media_playback" and act.get("title"):
                return act
        return None

    def get_context_key(self) -> str:
        """Returns the primary context identifier: e.g. 'vlc', 'excel', 'chrome', 'youtube', or 'global'."""
        if self.website:
            return self.website
        if self.application:
            return self.application
        if self.current_workflow:
            return self.current_workflow.lower()
        return "global"


# Backward compatible aliases
ActiveWebsiteContext = ActiveTargetContext
DesktopContext = ActiveTargetContext


@dataclass
class TaskContext:
    """
    Authoritative context for the currently executing or pending task/workflow.
    Tracks active intent, targets, dynamic slots, and pending confirmations.
    """
    active_intent: Optional[str] = None
    active_target: Optional[str] = None
    workflow: str = ""
    slots: Dict[str, Any] = field(default_factory=dict)
    active_task_id: Optional[str] = None
    active_question: Optional[str] = None
    pending_goal: Optional[str] = None
    missing_slots: List[str] = field(default_factory=list)
    pending_clarification: Optional[str] = None
    pending_confirmation: Optional[Dict[str, Any]] = None
    updated_at: float = field(default_factory=time.time)

    def set_slot(self, slot_name: str, value: Any) -> None:
        self.slots[slot_name] = value
        self.updated_at = time.time()

    def get_slot(self, slot_name: str, default: Any = None) -> Any:
        return self.slots.get(slot_name, default)

    def clear(self) -> None:
        self.active_intent = None
        self.active_target = None
        self.workflow = ""
        self.slots.clear()
        self.active_task_id = None
        self.active_question = None
        self.pending_goal = None
        self.missing_slots.clear()
        self.pending_clarification = None
        self.pending_confirmation = None
        self.updated_at = time.time()


@dataclass
class AudioStateContext:
    """Authoritative context for active audio input/output devices and headset state."""
    input_device: Optional[str] = None
    input_device_index: Optional[int] = None
    output_device: Optional[str] = None
    output_device_index: Optional[int] = None
    active_input_device: Optional[str] = None
    active_output_device: Optional[str] = None
    pygame_output_name: Optional[str] = None
    previous_input_device: Optional[str] = None
    previous_output_device: Optional[str] = None
    preferred_headset: Optional[str] = None
    is_headset_active: bool = False
    is_headset_connected: bool = False
    headset_name: Optional[str] = None
    has_microphone: bool = True
    has_speaker: bool = True
    auto_switch_enabled: bool = True
    connection_state: str = "STABLE"  # STABLE, SWITCHING, ACTIVE_HEADSET, FALLING_BACK, RECOVERED
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.active_input_device and not self.input_device:
            self.input_device = self.active_input_device
        if self.input_device and not self.active_input_device:
            self.active_input_device = self.input_device
        if self.active_output_device and not self.output_device:
            self.output_device = self.active_output_device
        if self.output_device and not self.active_output_device:
            self.active_output_device = self.output_device
        if self.is_headset_connected:
            self.is_headset_active = True
        elif self.is_headset_active:
            self.is_headset_connected = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_device": self.input_device,
            "input_device_index": self.input_device_index,
            "output_device": self.output_device,
            "output_device_index": self.output_device_index,
            "active_input_device": self.active_input_device,
            "active_output_device": self.active_output_device,
            "pygame_output_name": self.pygame_output_name,
            "previous_input_device": self.previous_input_device,
            "previous_output_device": self.previous_output_device,
            "preferred_headset": self.preferred_headset,
            "is_headset_active": self.is_headset_active or self.is_headset_connected,
            "is_headset_connected": self.is_headset_connected or self.is_headset_active,
            "headset_name": self.headset_name,
            "has_microphone": self.has_microphone,
            "has_speaker": self.has_speaker,
            "auto_switch_enabled": self.auto_switch_enabled,
            "connection_state": self.connection_state,
            "updated_at": self.updated_at
        }


class RuntimeContext:
    """
    Single Authoritative Runtime Context for Jarvis V2.
    Unifies SessionContext, DesktopContext, TaskContext, UserContext, and AudioStateContext into
    one coherent, observable hierarchy without duplicate or conflicting state.
    """

    _instance: Optional["RuntimeContext"] = None

    @classmethod
    def get_instance(cls) -> "RuntimeContext":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "RuntimeContext") -> None:
        cls._instance = instance

    def __init__(
        self,
        session: Optional[SessionContext] = None,
        desktop: Optional[ActiveTargetContext] = None,
        task: Optional[TaskContext] = None,
        user: Optional[UserContext] = None,
        audio: Optional[AudioStateContext] = None,
    ):
        RuntimeContext._instance = self
        self.session: SessionContext = session or SessionContext()
        self.desktop: ActiveTargetContext = desktop or ActiveTargetContext()
        self.task: TaskContext = task or TaskContext()
        self.user: UserContext = user or UserContext()
        self.audio: AudioStateContext = audio or AudioStateContext()

    @property
    def active_context(self) -> ActiveTargetContext:
        """Backward compatibility accessor for legacy active_context callers."""
        return self.desktop

    @property
    def application(self) -> str:
        return self.desktop.application

    @property
    def website(self) -> str:
        return self.desktop.website

    @property
    def window(self) -> str:
        return self.desktop.window

    @property
    def current_workflow(self) -> str:
        return self.task.workflow or self.desktop.current_workflow

    def clear_transient_state(self) -> None:
        """Clears per-task transient state while preserving session history."""
        self.task.clear()
        self.desktop.clear()

    def clear_all(self) -> None:
        """Clears all session, task, and desktop runtime states."""
        self.session.clear()
        self.desktop.clear()
        self.task.clear()

