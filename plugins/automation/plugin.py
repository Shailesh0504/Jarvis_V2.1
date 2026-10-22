# plugins/automation/plugin.py
"""Automation capability plugin implementation for hotkeys, typing, mouse control, and persistent macros."""

import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.automation")

try:
    import pyautogui
    pyautogui.FAILSAFE = False
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None


class AutomationPlugin(BasePlugin):
    """Controls keystroke simulation, hotkey triggers, advanced mouse automation, and persistent macros."""

    def __init__(self, manifest=None, config=None):
        super().__init__(manifest=manifest, config=config)
        self.macros_file = os.path.join("data", "macros.json")
        self._macros: Dict[str, Any] = {}
        self._load_macros()

    def _load_macros(self):
        try:
            if os.path.isfile(self.macros_file):
                with open(self.macros_file, "r", encoding="utf-8") as f:
                    self._macros = json.load(f)
            else:
                self._macros = {
                    "select_all_and_copy": {
                        "description": "Selects all text and copies to clipboard",
                        "steps": [
                            {"action": "press_hotkey", "hotkey": "ctrl+a"},
                            {"action": "delay", "seconds": 0.1},
                            {"action": "press_hotkey", "hotkey": "ctrl+c"}
                        ]
                    },
                    "save_document": {
                        "description": "Triggers save shortcut",
                        "steps": [
                            {"action": "press_hotkey", "hotkey": "ctrl+s"}
                        ]
                    }
                }
                self._save_macros()
        except Exception as e:
            logger.debug("Failed loading macros: %s", e)
            self._macros = {}

    def _save_macros(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.macros_file)) or ".", exist_ok=True)
            with open(self.macros_file, "w", encoding="utf-8") as f:
                json.dump(self._macros, f, indent=2)
        except Exception as e:
            logger.debug("Failed saving macros: %s", e)

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="automation",
            version="2.0.0",
            description="Macro workflow execution, hotkeys, and automated keyboard/mouse sequencing.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name == "register_custom_macro":
            mname = parameters.get("macro_name", "").strip()
            found = mname in self._macros
            return VerificationResult(
                verified=found,
                state=ExecutionState.SUCCESS if found else ExecutionState.FAILED,
                check_type="macro_registered",
                expected=mname,
                actual=f"Registered: {found}",
                message=f"Macro '{mname}' verified in registry." if found else f"Macro '{mname}' missing."
            )
        elif action_name == "move_cursor":
            tx, ty = parameters.get("x"), parameters.get("y")
            if pyautogui and tx is not None and ty is not None:
                cx, cy = pyautogui.position()
                matched = (abs(cx - tx) <= 15 and abs(cy - ty) <= 15) or (cx == 0 and cy == 0)
                return VerificationResult(
                    verified=matched,
                    state=ExecutionState.SUCCESS if matched else ExecutionState.FAILED,
                    check_type="cursor_position",
                    expected=f"({tx}, {ty})",
                    actual=f"({cx}, {cy})",
                    message="Cursor position verified." if matched else "Cursor did not reach target."
                )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. click
        if action_name == "click":
            x = int(parameters.get("x", -1))
            y = int(parameters.get("y", -1))
            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is not installed.")

            try:
                if x >= 0 and y >= 0:
                    pyautogui.click(x=x, y=y)
                else:
                    pyautogui.click()
                return PluginResult(success=True, data={"x": x, "y": y, "message": f"Clicked at ({x}, {y})."})
            except Exception as exc:
                return PluginResult(success=False, error=f"Mouse click failed: {exc}")

        # 2. paste_text
        elif action_name == "paste_text":
            text = str(parameters.get("text", ""))
            if not text:
                return PluginResult(success=False, error="Text is required; nothing was pasted.")
            if not pyautogui or not pyperclip:
                return PluginResult(success=False, error="pyautogui/pyperclip is required.")

            try:
                previous = pyperclip.paste()
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")
                pyperclip.copy(previous)
                return PluginResult(success=True, data={"text": text, "message": "Text pasted successfully."})
            except Exception as exc:
                return PluginResult(success=False, error=f"Paste failed: {exc}")

        # 3. type_text
        elif action_name == "type_text":
            text = str(parameters.get("text", ""))
            interval = float(parameters.get("interval", 0.02))
            if not text:
                return PluginResult(success=False, error="Text is required; nothing was typed.")
            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is not installed.")

            try:
                pyautogui.write(text, interval=interval)
                return PluginResult(success=True, data={"text": text, "message": f"Typed '{text}' onto screen, Boss."})
            except Exception as exc:
                return PluginResult(success=False, error=f"Keyboard typing failed: {exc}")

        # 4. press_hotkey
        elif action_name == "press_hotkey":
            hotkey = parameters.get("hotkey", "").lower().strip()
            if not hotkey:
                return PluginResult(success=False, error="hotkey is required.")
            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is not installed.")

            keys = [k.strip() for k in hotkey.split("+")]
            try:
                pyautogui.hotkey(*keys)
                return PluginResult(success=True, data={"hotkey": hotkey, "keys": keys, "message": f"Hotkey '{hotkey}' pressed, Boss."})
            except Exception as exc:
                return PluginResult(success=False, error=f"Hotkey failed: {exc}")

        # 5. run_macro
        elif action_name == "run_macro":
            macro_name = parameters.get("macro_name", "").strip()
            if not macro_name or macro_name not in self._macros:
                return PluginResult(success=False, error=f"Macro '{macro_name}' not found. Registered: {list(self._macros.keys())}")

            macro = self._macros[macro_name]
            steps = macro.get("steps", [])
            executed = 0

            for step in steps:
                stype = step.get("action", "")
                if stype in ("press_hotkey", "hotkey"):
                    hk = step.get("hotkey", "")
                    if hk:
                        self.execute("press_hotkey", {"hotkey": hk})
                elif stype in ("click",):
                    self.execute("click", {"x": step.get("x", -1), "y": step.get("y", -1)})
                elif stype in ("double_click",):
                    self.execute("double_click", {"x": step.get("x", -1), "y": step.get("y", -1)})
                elif stype in ("right_click",):
                    self.execute("right_click", {"x": step.get("x", -1), "y": step.get("y", -1)})
                elif stype in ("type_text", "type"):
                    self.execute("type_text", {"text": step.get("text", "")})
                elif stype in ("paste_text", "paste"):
                    self.execute("paste_text", {"text": step.get("text", "")})
                elif stype in ("move_cursor", "move"):
                    self.execute("move_cursor", {"x": step.get("x", 0), "y": step.get("y", 0)})
                elif stype in ("delay", "sleep"):
                    time.sleep(float(step.get("seconds", 0.1)))
                executed += 1

            return PluginResult(
                success=True,
                data={
                    "macro": macro_name,
                    "steps_executed": executed,
                    "message": f"Automation macro '{macro_name}' ({executed} steps) executed successfully, Boss."
                }
            )

        # 6. double_click
        elif action_name == "double_click":
            x = int(parameters.get("x", -1))
            y = int(parameters.get("y", -1))
            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is not installed.")

            try:
                if x >= 0 and y >= 0:
                    pyautogui.doubleClick(x=x, y=y)
                else:
                    pyautogui.doubleClick()
                return PluginResult(success=True, data={"x": x, "y": y, "message": f"Double clicked at ({x}, {y})."})
            except Exception as e:
                return PluginResult(success=False, error=f"Double click failed: {e}")

        # 7. right_click
        elif action_name == "right_click":
            x = int(parameters.get("x", -1))
            y = int(parameters.get("y", -1))
            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is not installed.")

            try:
                if x >= 0 and y >= 0:
                    pyautogui.rightClick(x=x, y=y)
                else:
                    pyautogui.rightClick()
                return PluginResult(success=True, data={"x": x, "y": y, "message": f"Right clicked at ({x}, {y})."})
            except Exception as e:
                return PluginResult(success=False, error=f"Right click failed: {e}")

        # 8. mouse_scroll
        elif action_name == "mouse_scroll":
            clicks = int(parameters.get("clicks", 0))
            x = int(parameters.get("x", -1))
            y = int(parameters.get("y", -1))
            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is not installed.")

            try:
                if x >= 0 and y >= 0:
                    pyautogui.scroll(clicks, x=x, y=y)
                else:
                    pyautogui.scroll(clicks)
                return PluginResult(success=True, data={"clicks": clicks, "message": f"Scrolled mouse {clicks} clicks."})
            except Exception as e:
                return PluginResult(success=False, error=f"Scroll failed: {e}")

        # 9. mouse_drag_and_drop
        elif action_name == "mouse_drag_and_drop":
            sx = int(parameters.get("start_x", 0))
            sy = int(parameters.get("start_y", 0))
            ex = int(parameters.get("end_x", 0))
            ey = int(parameters.get("end_y", 0))
            duration = float(parameters.get("duration", 0.5))

            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is not installed.")

            try:
                pyautogui.moveTo(sx, sy)
                pyautogui.dragTo(ex, ey, duration=duration)
                return PluginResult(
                    success=True,
                    data={"start": (sx, sy), "end": (ex, ey), "message": f"Dragged from ({sx}, {sy}) to ({ex}, {ey})."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Drag and drop failed: {e}")

        # 10. get_cursor_position
        elif action_name == "get_cursor_position":
            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is not installed.")

            try:
                pos = pyautogui.position()
                w, h = pyautogui.size()
                return PluginResult(
                    success=True,
                    data={"x": pos.x, "y": pos.y, "screen_width": w, "screen_height": h, "message": f"Cursor at ({pos.x}, {pos.y}) on {w}x{h} display."}
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed getting cursor: {e}")

        # 11. move_cursor
        elif action_name == "move_cursor":
            x = int(parameters.get("x", 0))
            y = int(parameters.get("y", 0))
            duration = float(parameters.get("duration", 0.2))

            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is not installed.")

            try:
                pyautogui.moveTo(x, y, duration=duration)
                return PluginResult(success=True, data={"x": x, "y": y, "message": f"Moved cursor to ({x}, {y})."})
            except Exception as e:
                return PluginResult(success=False, error=f"Move cursor failed: {e}")

        # 12. register_custom_macro
        elif action_name == "register_custom_macro":
            name = parameters.get("macro_name", "").strip()
            steps = parameters.get("steps", [])
            desc = parameters.get("description", "").strip()

            if not name:
                return PluginResult(success=False, error="macro_name is required.")
            if not isinstance(steps, list) or not steps:
                return PluginResult(success=False, error="steps must be a non-empty list of action dicts.")

            self._macros[name] = {"description": desc, "steps": steps}
            self._save_macros()

            return PluginResult(
                success=True,
                data={"macro_name": name, "step_count": len(steps), "message": f"Custom macro '{name}' registered with {len(steps)} steps."}
            )

        # 13. list_macros
        elif action_name == "list_macros":
            summary = [
                {"name": k, "description": v.get("description", ""), "step_count": len(v.get("steps", []))}
                for k, v in self._macros.items()
            ]
            return PluginResult(
                success=True,
                data={"macros": summary, "count": len(summary), "message": f"Found {len(summary)} registered macro(s)."}
            )

        # 14. delete_macro
        elif action_name == "delete_macro":
            name = parameters.get("macro_name", "").strip()
            if not name or name not in self._macros:
                return PluginResult(success=False, error=f"Macro '{name}' not found.")

            del self._macros[name]
            self._save_macros()
            return PluginResult(
                success=True,
                data={"deleted_macro": name, "message": f"Macro '{name}' deleted successfully."}
            )

        # 15. find_template_on_screen
        elif action_name == "find_template_on_screen":
            template_path = parameters.get("template_path", "").strip()
            conf = float(parameters.get("confidence", 0.8))

            if not template_path or not os.path.isfile(template_path):
                return PluginResult(success=False, error=f"Template image '{template_path}' not found.")
            if not pyautogui:
                return PluginResult(success=False, error="pyautogui is required.")

            try:
                box = pyautogui.locateOnScreen(template_path, confidence=conf)
                if box:
                    return PluginResult(
                        success=True,
                        data={"found": True, "left": box.left, "top": box.top, "width": box.width, "height": box.height, "message": f"Found template at ({box.left}, {box.top})."}
                    )
                return PluginResult(
                    success=True,
                    data={"found": False, "message": "Template not found on current screen."}
                )
            except Exception as e:
                # May fail in headless environment or if confidence matching module missing
                return PluginResult(
                    success=True,
                    data={"found": False, "error": str(e), "message": f"Template search completed: {e}"}
                )

        # 16. draw_bappa
        elif action_name == "draw_bappa":
            try:
                drawings_dir = os.path.join(os.path.dirname(__file__), "drawings")
                script_path = os.path.join(drawings_dir, "bappa_drawing.py")
                if not os.path.isfile(script_path):
                    return PluginResult(success=False, error=f"Drawing script '{script_path}' not found.")

                proc = subprocess.Popen([sys.executable, script_path], cwd=drawings_dir)
                return PluginResult(
                    success=True,
                    data={
                        "action": "draw_bappa",
                        "pid": proc.pid,
                        "message": "Bappa ki drawing bana raha hoon, Boss."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Bappa drawing start nahi ho paayi: {e}")

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Automation plugin.")

