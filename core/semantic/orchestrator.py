# core/semantic/orchestrator.py
"""Central pipeline orchestrator dispatching user queries through specialized parsers."""

from typing import Any, Optional

from core.semantic.gating import should_bypass_command_parsing
from core.semantic.models import SemanticAction
from core.semantic.parsers.aliases import parse_alias_management, parse_custom_alias_execution
from core.semantic.parsers.math_parser import parse_math
from core.semantic.parsers.media import (
    parse_activity_and_media_query,
    parse_media_playback,
    parse_media_search,
    parse_youtube_control,
)
from core.semantic.parsers.memory import parse_memory_command
from core.semantic.parsers.productivity import (
    parse_location,
    parse_reminder,
    parse_time_date,
    parse_whatsapp,
)
from core.semantic.parsers.security import parse_password_generation
from core.semantic.parsers.system import (
    parse_audio_control,
    parse_bluetooth_control,
    parse_face_auth,
    parse_network,
    parse_screen_control,
    parse_screen_inspection,
    parse_status_query,
    parse_system_control,
    parse_system_maintenance,
    parse_software_update,
    parse_equity_research,
    parse_code_assistant,
)
from core.semantic.parsers.web import (
    parse_generic_web_search,
    parse_generic_website_open,
    parse_known_website,
    parse_network_share,
    parse_product_discovery_and_web_search,
)
from core.semantic.parsers.windows import (
    parse_app_close,
    parse_file_delete,
    parse_file_open,
    parse_folder_management,
    parse_service_open,
    parse_universal_target_action,
    parse_window_control,
    parse_window_layout,
)


class SemanticPipelineOrchestrator:
    """
    Coordinates modular semantic parsers across the NLU pipeline.
    Maintains exact priority ordering with sub-millisecond execution.
    """

    @classmethod
    def resolve_semantic_goal(cls, user_input: str, context: Optional[object] = None) -> Any:
        """
        Derives the 11-field unified semantic decision model (meaning, goal, capability, decision).
        """
        from core.semantic.goal_resolver import UniversalGoalResolver
        return UniversalGoalResolver.resolve(user_input, context=context)

    @classmethod
    def parse(cls, user_input: str, context: Optional[object] = None) -> Optional[SemanticAction]:
        """
        Parses user query into a structured SemanticAction.
        Returns None if query is purely conversational or doesn't match a command.
        """
        raw_text = user_input.strip()
        lowered = raw_text.lower()

        # Pre-normalize known STT phonetic and keyboard errors
        from core.semantic.normalizer import HinglishNormalizer
        normalized_query = HinglishNormalizer.normalize_text(lowered)
        effective_lowered = normalized_query if normalized_query else lowered

        # High-confidence silent spelling resolution for direct parser calls
        try:
            from brain.spelling_resolver import SpellingResolver
            sp_res = SpellingResolver.resolve(effective_lowered)
            if sp_res and not sp_res.needs_confirmation and sp_res.confidence >= 0.85:
                effective_lowered = sp_res.corrected_text
        except Exception:
            pass

        # 1. Conversational greetings, jokes, stories, and verbal correction gating
        if should_bypass_command_parsing(lowered) or should_bypass_command_parsing(effective_lowered):
            return None

        # 2. UNC / Network share paths
        network_share_action = parse_network_share(raw_text)
        if network_share_action:
            return network_share_action

        # 3. Math & Calculation Intents
        math_action = parse_math(raw_text, lowered)
        if math_action:
            return math_action

        # 4. Time & Date Intents
        time_action = parse_time_date(raw_text, effective_lowered)
        if time_action:
            return time_action

        # 5. System Control (Restart, Shutdown, Lock, Sleep)
        system_action = parse_system_control(raw_text, effective_lowered)
        if system_action:
            return system_action

        # 5b. Explicit Memory Control (remember/forget/recall — runs BEFORE
        # reminders so "yaad rakho ..." stores memory while "yaad dilana ..."
        # still routes to reminders; profiles/commands keep their owners).
        memory_action = parse_memory_command(raw_text, effective_lowered)
        if memory_action:
            return memory_action

        # 6. Reminder Intents (Create, List, Cancel, Snooze, Toggle)
        reminder_action = parse_reminder(raw_text, effective_lowered)
        if reminder_action:
            return reminder_action

        # 7. Network diagnostics and Wi-Fi speed/passwords
        network_action = parse_network(raw_text, effective_lowered)
        if network_action:
            return network_action

        # 7b. Security & Password Generation Intents
        pwd_action = parse_password_generation(raw_text, effective_lowered)
        if pwd_action:
            return pwd_action

        # 8. Screen Inspection
        screen_insp = parse_screen_inspection(raw_text, effective_lowered)
        if screen_insp:
            return screen_insp

        # 8a. Developer Code Assistant
        code_action = parse_code_assistant(raw_text, effective_lowered, context=context)
        if code_action:
            return code_action

        # 8b. Visual Text Interaction (Find Text, Point, Click, Double-Click, Select)
        from core.semantic.parsers.visual import parse_visual_text_interaction
        visual_action = parse_visual_text_interaction(raw_text, effective_lowered)
        if visual_action:
            return visual_action

        # 9. Past Activity & Media Query
        activity_action = parse_activity_and_media_query(raw_text, effective_lowered)
        if activity_action:
            return activity_action

        # 10. Status Query
        status_action = parse_status_query(raw_text, effective_lowered)
        if status_action:
            return status_action

        # 11. Face Biometrics & Security Authentication
        face_action = parse_face_auth(raw_text, effective_lowered)
        if face_action:
            return face_action

        # 12. User-Learned Website & Application Alias Management
        alias_mgmt = parse_alias_management(raw_text, effective_lowered)
        if alias_mgmt:
            return alias_mgmt

        # 13. User-Learned Custom Alias Execution
        alias_exec = parse_custom_alias_execution(raw_text, effective_lowered)
        if alias_exec:
            return alias_exec

        # 14. Universal Target Action
        target_action = parse_universal_target_action(raw_text, effective_lowered)
        if target_action:
            return target_action

        # 15. Known Websites
        known_website = parse_known_website(raw_text, effective_lowered)
        if known_website:
            return known_website

        # 16. YouTube Session Controls
        youtube_control = parse_youtube_control(raw_text, effective_lowered)
        if youtube_control:
            return youtube_control

        # 17. Media Playback Intent (YouTube / VLC)
        play_action = parse_media_playback(raw_text, effective_lowered, context=context)
        if play_action:
            return play_action

        # 18. Media Search Intent (YouTube search)
        search_action = parse_media_search(raw_text, effective_lowered)
        if search_action:
            return search_action

        # 19. Product Discovery & Site-Aware Web Search
        web_discovery = parse_product_discovery_and_web_search(raw_text, effective_lowered)
        if web_discovery:
            return web_discovery

        # 20. Window Layout & Positioning
        layout_action = parse_window_layout(raw_text, effective_lowered)
        if layout_action:
            return layout_action

        # 21. Folder Management (Daily-use & named folders - Priority 3a)
        folder_action = parse_folder_management(raw_text, effective_lowered)
        if folder_action:
            return folder_action

        # 22. Service & Local Application Open Intent (Priority 1 & 2)
        open_action = parse_service_open(raw_text, effective_lowered)
        if open_action:
            return open_action

        # 23. File / Document Open Intent (Priority 3b)
        file_action = parse_file_open(raw_text, effective_lowered)
        if file_action:
            return file_action

        # 23b. File Delete Intent (after open/close: file-scoped only, HIGH risk
        # gating stays downstream in policy/confirmation)
        delete_action = parse_file_delete(raw_text, effective_lowered)
        if delete_action:
            return delete_action

        # 24. App Close Intent (specific resolver with process names;
        # must run BEFORE generic window control so "opencode band karo"
        # resolves to OpenCode, not substring "code")
        close_action = parse_app_close(raw_text, effective_lowered)
        if close_action:
            return close_action

        # 25. Generic Window Control fallback
        window_action = parse_window_control(raw_text, effective_lowered)
        if window_action:
            return window_action

        # 26. System Maintenance
        maintenance_action = parse_system_maintenance(effective_lowered, context=context)
        if maintenance_action:
            return maintenance_action

        # 26b. Software & System Updates
        update_action = parse_software_update(raw_text, effective_lowered, context=context)
        if update_action:
            return update_action

        # 26c. Indian Equity Research & Decision Support
        equity_action = parse_equity_research(raw_text, effective_lowered, context=context)
        if equity_action:
            return equity_action

        # 27. Audio Control Intent
        audio_action = parse_audio_control(raw_text, effective_lowered)
        if audio_action:
            return audio_action

        # 28. Screen Control Intent
        screen_action = parse_screen_control(raw_text, effective_lowered)
        if screen_action:
            return screen_action

        # 29. Bluetooth Intent
        bt_action = parse_bluetooth_control(raw_text, effective_lowered)
        if bt_action:
            return bt_action

        # 30. Location / Geography Intent
        loc_action = parse_location(raw_text, effective_lowered)
        if loc_action:
            return loc_action

        # 31. WhatsApp Messaging / Calling Intent
        wa_action = parse_whatsapp(raw_text, effective_lowered)
        if wa_action:
            return wa_action

        # 32. Generic Website Open (Priority 4)
        website_action = parse_generic_website_open(raw_text, effective_lowered)
        if website_action:
            return website_action

        # 33. Fallback Web Search (Priority 5)
        web_search_action = parse_generic_web_search(effective_lowered)
        if web_search_action:
            return web_search_action


        return None
