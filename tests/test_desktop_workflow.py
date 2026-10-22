# tests/test_desktop_workflow.py
"""Regression coverage for generic, verified desktop action orchestration."""

from types import SimpleNamespace

from core.desktop_workflow import (
    DesktopAction, DesktopActionPlanner, DesktopWorkflowCoordinator,
    DesktopWorkflowExecutor, WorkflowState,
)
from plugins.manifest import PluginResult
from plugins.windows.window_manager import WindowInfo


class FakeWindowManager:
    def __init__(self, available=True, correct_focus=True):
        self.available = available
        self.correct_focus = correct_focus
        self._user32 = object()
        self.target = WindowInfo(101, "Untitled - Notepad", "notepad.exe", 10)
        self.other = WindowInfo(202, "Other", "other.exe", 20)

    def find_windows_for_app(self, _target):
        return [self.target] if self.available else []

    def get_foreground_window(self):
        return self.target if self.correct_focus else self.other


class FakePluginManager:
    def __init__(self, launch_success=True, available=True, correct_focus=True):
        self.calls = []
        self.launch_success = launch_success
        self.window_manager = FakeWindowManager(available, correct_focus)
        self.windows_plugin = SimpleNamespace(window_manager=self.window_manager)

    def get_plugin(self, name):
        return self.windows_plugin if name == "windows" else None

    def execute_action(self, plugin, action, parameters):
        self.calls.append((plugin, action, dict(parameters)))
        if plugin == "windows" and action == "launch_app" and not self.launch_success:
            return PluginResult(success=False, error="application launch failed")
        return PluginResult(success=True, data={"plugin": plugin, "action": action})


class FakeTime:
    def __init__(self, executor_to_cancel=None):
        self.value = 0.0
        self.executor_to_cancel = executor_to_cancel

    def clock(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds
        if self.executor_to_cancel:
            self.executor_to_cancel.cancel()


def test_planner_creates_ordered_open_wait_focus_type_actions():
    plan = DesktopActionPlanner().parse("open Notepad and type Hello Boss")
    assert plan is not None
    assert [step.action for step in plan.steps] == [
        DesktopAction.OPEN, DesktopAction.WAIT_FOR_WINDOW, DesktopAction.FOCUS, DesktopAction.TYPE,
    ]
    assert plan.steps[-1].parameters["text"] == "Hello Boss"
    assert plan.steps[-1].depends_on == [plan.steps[-2].step_id]


def test_hinglish_and_reusable_application_variants_parse_generically():
    planner = DesktopActionPlanner()
    notepad = planner.parse("Notepad kholo aur Hello likho")
    chrome = planner.parse("Chrome kholo aur YouTube search karo")
    excel = planner.parse("open Excel and open Sales.xlsx")
    assert notepad.steps[-1].parameters["text"] == "Hello"
    assert [step.action for step in chrome.steps[-2:]] == [DesktopAction.TYPE, DesktopAction.HOTKEY]
    assert chrome.steps[-2].parameters["text"] == "YouTube"
    assert [step.action for step in excel.steps[-3:]] == [DesktopAction.HOTKEY, DesktopAction.TYPE, DesktopAction.HOTKEY]
    assert excel.steps[-2].parameters["text"] == "Sales.xlsx"


def test_missing_text_asks_and_resumes_without_typing_arbitrary_content():
    manager = FakePluginManager()
    coordinator = DesktopWorkflowCoordinator(manager)
    handled, response, result = coordinator.try_handle("open notepad and start typing")
    assert handled and response == "Kya type karna hai?" and result is None
    assert manager.calls == []
    handled, response, result = coordinator.try_handle("Hello Boss")
    assert handled and result.success
    assert ("automation", "type_text", {"text": "Hello Boss"}) in manager.calls


def test_launch_failure_stops_dependent_actions():
    manager = FakePluginManager(launch_success=False)
    plan = DesktopActionPlanner().parse("open Notepad and type Hello")
    result = DesktopWorkflowExecutor(manager, sleep_fn=lambda _: None).execute(plan)
    assert result.state == WorkflowState.FAILED
    assert len(manager.calls) == 2  # one initial attempt + one configured retry
    assert all(call[1] == "launch_app" for call in manager.calls)


def test_wrong_window_focus_prevents_typing():
    manager = FakePluginManager(correct_focus=False)
    plan = DesktopActionPlanner().parse("open Notepad and type Secret")
    result = DesktopWorkflowExecutor(manager, sleep_fn=lambda _: None).execute(plan)
    assert result.state == WorkflowState.FAILED
    assert "Wrong window focused" in result.error
    assert not any(call[1] == "type_text" for call in manager.calls)


def test_window_timeout_stops_workflow():
    manager = FakePluginManager(available=False)
    fake_time = FakeTime()
    plan = DesktopActionPlanner().parse("open Notepad and type Hello")
    plan.steps[1].timeout_seconds = 0.3
    executor = DesktopWorkflowExecutor(manager, sleep_fn=fake_time.sleep, clock=fake_time.clock)
    result = executor.execute(plan)
    assert result.state == WorkflowState.FAILED
    assert "Timed out waiting" in result.error
    assert not any(call[1] == "type_text" for call in manager.calls)


def test_user_cancellation_interrupts_wait_loop():
    manager = FakePluginManager(available=False)
    executor = DesktopWorkflowExecutor(manager)
    fake_time = FakeTime(executor)
    executor.sleep, executor.clock = fake_time.sleep, fake_time.clock
    plan = DesktopActionPlanner().parse("open Notepad and type Hello")
    result = executor.execute(plan)
    assert result.state == WorkflowState.CANCELLED
    assert not any(call[1] == "type_text" for call in manager.calls)


def test_explicit_desktop_action_vocabulary_is_distinct():
    expected = {"OPEN", "FOCUS", "TYPE", "CLICK", "HOTKEY", "WAIT", "READ_SCREEN",
                "SELECT_TEXT", "PASTE", "SAVE", "WAIT_FOR_WINDOW", "OPEN_FILE", "SEARCH"}
    assert expected == {action.value for action in DesktopAction}
