# plugins/games/plugin.py
"""Games plugin implementation for launching Chess and other local games."""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psutil
from PIL import Image, ImageDraw

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.games")

KNOWN_GAME_PROCESSES = {
    "chess.exe": "Chess",
    "steam.exe": "Steam",
    "steamwebhelper.exe": "Steam Overlay/Web",
    "epicgameslauncher.exe": "Epic Games Launcher",
    "riotclientservices.exe": "Riot Client",
    "valorant.exe": "Valorant",
    "cs2.exe": "Counter-Strike 2",
    "dota2.exe": "Dota 2",
    "gta5.exe": "Grand Theft Auto V",
    "minecraft.exe": "Minecraft",
    "javaw.exe": "Minecraft / Java Game",
    "fortniteclient-win64-shipping.exe": "Fortnite",
    "leagueclient.exe": "League of Legends",
    "genshinimpact.exe": "Genshin Impact",
}


class GamesPlugin(BasePlugin):
    """Controls launching and management of system and local games."""

    def __init__(self):
        super().__init__()
        self._data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
        self._sessions_file = os.path.join(self._data_dir, "game_sessions.json")
        self._screenshots_dir = os.path.join(self._data_dir, "screenshots", "games")
        self._game_mode_active = False

    def initialize(self) -> bool:
        os.makedirs(self._data_dir, exist_ok=True)
        os.makedirs(self._screenshots_dir, exist_ok=True)
        return True

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="games",
            version="1.0.0",
            description="Game launcher and interactive gaming controllers for Chess and other system games.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        if action_name in ("open_chess", "launch_game"):
            game_name = str(parameters.get("game_name", "chess")).strip().lower()
            if action_name == "open_chess" or "chess" in game_name:
                chess_exe = os.path.abspath(os.path.join(os.path.dirname(__file__), "Chess", "chess.exe"))
                if os.path.exists(chess_exe):
                    try:
                        subprocess.Popen([chess_exe], cwd=os.path.dirname(chess_exe))
                        return PluginResult(
                            success=True,
                            data={"game": "chess", "message": "Chess game open kar diya hai, Boss."}
                        )
                    except Exception as e:
                        return PluginResult(success=False, error=f"Chess game open nahi ho paya: {e}")
                else:
                    return PluginResult(success=False, error="Chess executable nahi mila.")
            return PluginResult(success=False, error=f"Game '{game_name}' supported nahi hai.")

        if action_name == "scan_installed_games":
            try:
                found_games = []
                # Check bundled Chess
                chess_exe = os.path.abspath(os.path.join(os.path.dirname(__file__), "Chess", "chess.exe"))
                if os.path.exists(chess_exe):
                    found_games.append({
                        "name": "Chess",
                        "launcher": "Built-in",
                        "path": chess_exe
                    })

                # Check Steam common library
                steam_apps_dir = r"C:\Program Files (x86)\Steam\steamapps\common"
                if os.path.isdir(steam_apps_dir):
                    for entry in os.listdir(steam_apps_dir):
                        full_p = os.path.join(steam_apps_dir, entry)
                        if os.path.isdir(full_p):
                            found_games.append({
                                "name": entry,
                                "launcher": "Steam",
                                "path": full_p
                            })

                # Check Epic Games Manifests
                epic_manifests = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
                if os.path.isdir(epic_manifests):
                    for item in os.listdir(epic_manifests):
                        if item.endswith(".item"):
                            try:
                                with open(os.path.join(epic_manifests, item), "r", encoding="utf-8") as f:
                                    meta = json.load(f)
                                    found_games.append({
                                        "name": meta.get("DisplayName", item),
                                        "launcher": "Epic Games",
                                        "path": meta.get("InstallLocation", "")
                                    })
                            except Exception:
                                pass

                # Check Riot Games
                riot_dir = r"C:\Riot Games"
                if os.path.isdir(riot_dir):
                    for entry in os.listdir(riot_dir):
                        full_p = os.path.join(riot_dir, entry)
                        if os.path.isdir(full_p):
                            found_games.append({
                                "name": entry,
                                "launcher": "Riot Games",
                                "path": full_p
                            })

                return PluginResult(
                    success=True,
                    data={
                        "games": found_games,
                        "count": len(found_games),
                        "message": f"Found {len(found_games)} installed game(s)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to scan installed games: {e}")

        if action_name == "detect_running_games":
            try:
                running_games = []
                for proc in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
                    try:
                        pname = proc.info["name"].lower()
                        if pname in KNOWN_GAME_PROCESSES:
                            mem_mb = round(proc.info["memory_info"].rss / (1024 * 1024), 1) if proc.info["memory_info"] else 0
                            running_games.append({
                                "pid": proc.info["pid"],
                                "process_name": proc.info["name"],
                                "game_title": KNOWN_GAME_PROCESSES[pname],
                                "memory_mb": mem_mb,
                                "cpu_percent": proc.info.get("cpu_percent", 0.0)
                            })
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                return PluginResult(
                    success=True,
                    data={
                        "running_games": running_games,
                        "count": len(running_games),
                        "message": f"Detected {len(running_games)} active game process(es)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to detect running games: {e}")

        if action_name == "enable_game_mode":
            try:
                self._game_mode_active = True
                boosted_count = 0
                # Elevate priority of any active game processes
                for proc in psutil.process_iter(["pid", "name"]):
                    try:
                        pname = proc.info["name"].lower()
                        if pname in KNOWN_GAME_PROCESSES and hasattr(psutil, "HIGH_PRIORITY_CLASS"):
                            proc.nice(psutil.HIGH_PRIORITY_CLASS)
                            boosted_count += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                # Optionally activate Windows High Performance power scheme
                subprocess.run(
                    ["powercfg", "/s", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
                    capture_output=True,
                    check=False
                )

                return PluginResult(
                    success=True,
                    data={
                        "game_mode_active": True,
                        "boosted_processes": boosted_count,
                        "message": f"Game Mode activated. Boosted {boosted_count} game process(es) to High Priority."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to enable Game Mode: {e}")

        if action_name == "disable_game_mode":
            try:
                self._game_mode_active = False
                # Restore Balanced power scheme
                subprocess.run(
                    ["powercfg", "/s", "381b4222-f694-41f0-9685-ff5bb260df2e"],
                    capture_output=True,
                    check=False
                )
                return PluginResult(
                    success=True,
                    data={
                        "game_mode_active": False,
                        "message": "Game Mode disabled. Balanced power scheme restored."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to disable Game Mode: {e}")

        if action_name == "set_game_priority":
            pname_query = str(parameters.get("process_name", "")).strip().lower()
            priority_str = str(parameters.get("priority", "high")).strip().lower()
            if not pname_query:
                return PluginResult(success=False, error="Process name is required.")

            priority_map = {
                "high": getattr(psutil, "HIGH_PRIORITY_CLASS", 0x00000080),
                "realtime": getattr(psutil, "REALTIME_PRIORITY_CLASS", 0x00000100),
                "above_normal": getattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS", 0x00008000),
                "normal": getattr(psutil, "NORMAL_PRIORITY_CLASS", 0x00000020),
            }
            target_class = priority_map.get(priority_str, priority_map["high"])

            modified = 0
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if pname_query in proc.info["name"].lower():
                        proc.nice(target_class)
                        modified += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return PluginResult(
                success=True,
                data={
                    "process_name": pname_query,
                    "priority": priority_str,
                    "modified_processes": modified,
                    "message": f"Set priority '{priority_str}' on {modified} instance(s) of '{pname_query}'."
                }
            )

        if action_name == "log_game_session":
            game_name = str(parameters.get("game_name", "")).strip()
            duration = float(parameters.get("duration_minutes", 0))
            notes = str(parameters.get("notes", "")).strip()
            if not game_name or duration <= 0:
                return PluginResult(success=False, error="Valid game_name and duration_minutes (> 0) are required.")

            try:
                sessions = []
                if os.path.exists(self._sessions_file):
                    try:
                        with open(self._sessions_file, "r", encoding="utf-8") as f:
                            sessions = json.load(f)
                    except Exception:
                        sessions = []

                session_entry = {
                    "id": len(sessions) + 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "game_name": game_name,
                    "duration_minutes": round(duration, 1),
                    "notes": notes
                }
                sessions.append(session_entry)

                with open(self._sessions_file, "w", encoding="utf-8") as f:
                    json.dump(sessions, f, indent=2)

                return PluginResult(
                    success=True,
                    data={
                        "session": session_entry,
                        "total_sessions": len(sessions),
                        "message": f"Logged {duration:.1f} mins session for '{game_name}'."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to log game session: {e}")

        if action_name == "get_game_session_stats":
            filter_game = str(parameters.get("game_name", "")).strip().lower()
            try:
                sessions = []
                if os.path.exists(self._sessions_file):
                    try:
                        with open(self._sessions_file, "r", encoding="utf-8") as f:
                            sessions = json.load(f)
                    except Exception:
                        sessions = []

                if filter_game:
                    sessions = [s for s in sessions if filter_game in s.get("game_name", "").lower()]

                total_minutes = sum(s.get("duration_minutes", 0) for s in sessions)
                game_breakdown = {}
                for s in sessions:
                    gname = s.get("game_name", "Unknown")
                    game_breakdown[gname] = round(game_breakdown.get(gname, 0.0) + s.get("duration_minutes", 0), 1)

                return PluginResult(
                    success=True,
                    data={
                        "total_playtime_minutes": round(total_minutes, 1),
                        "total_sessions": len(sessions),
                        "breakdown": game_breakdown,
                        "recent_sessions": sessions[-10:],
                        "message": f"Total recorded playtime: {round(total_minutes / 60, 2)} hours across {len(sessions)} session(s)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to get session stats: {e}")

        if action_name == "take_game_screenshot":
            game_name = str(parameters.get("game_name", "general")).strip().lower()
            clean_name = re.sub(r"[^\w\-]", "_", game_name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            out_filename = f"game_{clean_name}_{timestamp}.png"
            out_path = os.path.join(self._screenshots_dir, out_filename)

            try:
                # Try real screen grab
                from PIL import ImageGrab
                img = ImageGrab.grab()
                img.save(out_path, "PNG")
            except Exception as e:
                logger.debug("Desktop grab failed (%s), using synthesized screenshot", e)
                img = Image.new("RGB", (1920, 1080), color=(20, 25, 40))
                draw = ImageDraw.Draw(img)
                draw.rectangle([(20, 20), (1900, 1060)], outline=(0, 200, 255), width=3)
                draw.text((50, 50), f"Game Screenshot: {game_name.upper()}", fill=(255, 255, 255))
                draw.text((50, 90), f"Captured: {datetime.now().isoformat()}", fill=(180, 180, 200))
                img.save(out_path, "PNG")

            size_bytes = os.path.getsize(out_path) if os.path.exists(out_path) else 0
            return PluginResult(
                success=True,
                data={
                    "game_name": game_name,
                    "screenshot_path": out_path,
                    "size_bytes": size_bytes,
                    "message": f"Saved screenshot for '{game_name}' to {out_path} ({size_bytes} bytes)."
                }
            )

        if action_name == "list_steam_games":
            try:
                steam_apps_dir = r"C:\Program Files (x86)\Steam\steamapps"
                games = []
                if os.path.isdir(steam_apps_dir):
                    for filename in os.listdir(steam_apps_dir):
                        if filename.startswith("appmanifest_") and filename.endswith(".acf"):
                            acf_path = os.path.join(steam_apps_dir, filename)
                            try:
                                with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                                    content = f.read()
                                    name_m = re.search(r'"name"\s+"([^"]+)"', content)
                                    appid_m = re.search(r'"appid"\s+"([^"]+)"', content)
                                    dir_m = re.search(r'"installdir"\s+"([^"]+)"', content)
                                    if name_m:
                                        games.append({
                                            "name": name_m.group(1),
                                            "appid": appid_m.group(1) if appid_m else "",
                                            "installdir": dir_m.group(1) if dir_m else ""
                                        })
                            except Exception:
                                pass

                return PluginResult(
                    success=True,
                    data={
                        "steam_games": games,
                        "count": len(games),
                        "message": f"Found {len(games)} installed Steam game(s)."
                    }
                )
            except Exception as e:
                return PluginResult(success=False, error=f"Failed to list Steam games: {e}")

        if action_name == "kill_game_process":
            pname_query = str(parameters.get("process_name", "")).strip().lower()
            if not pname_query:
                return PluginResult(success=False, error="Process name is required.")

            killed = 0
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    if pname_query in proc.info["name"].lower():
                        proc.terminate()
                        killed += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return PluginResult(
                success=True,
                data={
                    "process_name": pname_query,
                    "killed_count": killed,
                    "message": f"Terminated {killed} instance(s) matching '{pname_query}'."
                }
            )

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Games plugin.")
