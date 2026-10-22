# tests/test_unseen_natural_paraphrases_70.py
"""
Comprehensive test suite for 70 unseen, human-style paraphrases
testing natural, indirect, incomplete, and colloquial utterances.
Verifies goal, entity, context, capability, and anti-guessing boundaries.
"""

import pytest
from core.context import ActiveTargetContext
from core.semantic.goal_resolver import UniversalGoalResolver
from core.semantic.resolution import ResolutionDecision


class TestUnseenParaphrases70:
    """Tests all 70 user paraphrases across 6 levels and Sabse Hard 10."""

    # =========================================================================
    # Level 1 — Easy Paraphrase (1-10)
    # =========================================================================
    def test_level_1_easy_paraphrases(self):
        cases = [
            ("Bhai Chrome ko zara chala de.", "OPEN_APPLICATION", "windows.application.launch"),
            ("Mujhe browser kholna hai, Chrome hi theek rahega.", "OPEN_APPLICATION", "windows.application.launch"),
            ("YouTube tak le chalo.", "OPEN_WEBSITE", "browser.website.open"),
            ("Brave ko hata do screen se.", "CLOSE_APPLICATION", "windows.application.close"),
            ("Calculator ki zarurat hai, use khol do.", "OPEN_APPLICATION", "windows.application.launch"),
            ("Temporary files ka jo kachra pada hai na, use saaf kar do.", "TEMP_FILE_CLEANUP", "system.maintenance.temp_cleanup"),
            ("Computer ki temp wali cheezein nikaal do.", "TEMP_FILE_CLEANUP", "system.maintenance.temp_cleanup"),
            ("Recycle Bin mein jo pada hai usse nipta do.", "RECYCLE_BIN_CLEANUP", "system.maintenance.recycle_bin"),
            ("Aaj ka time bata zara.", "TIME_QUERY", "system.time.query"),
            ("Abhi mere system mein kya chal raha hai?", "QUERY_STATUS", "system.status"),
        ]
        for query, expected_goal, expected_cap in cases:
            res = UniversalGoalResolver.resolve(query)
            assert res.goal == expected_goal, f"Failed for '{query}': expected {expected_goal}, got {res.goal}"
            if expected_cap:
                assert expected_cap in res.capability_required, f"Failed cap for '{query}': expected {expected_cap}, got {res.capability_required}"

    # =========================================================================
    # Level 2 — Natural Human Speech (11-20)
    # =========================================================================
    def test_level_2_natural_human_speech(self):
        ctx_temp = ActiveTargetContext()
        ctx_temp.update_command_context(intent="TEMP_FILE_CLEANUP", action="clear_temp_files", entities={"target": "temp_files"})

        ctx_notepad = ActiveTargetContext()
        ctx_notepad.set_application("notepad")

        # 11-15: direct speech
        res11 = UniversalGoalResolver.resolve("Yaar browser open karne ka mann hai, Chrome chala de.")
        assert res11.goal == "OPEN_APPLICATION"
        assert res11.decision == ResolutionDecision.EXECUTE

        res12 = UniversalGoalResolver.resolve("Mujhe YouTube dekhna hai, tu setup kar de.")
        assert res12.goal == "OPEN_WEBSITE"

        res13 = UniversalGoalResolver.resolve("Jo temporary junk pada hua hai usko thoda clean kar.")
        assert res13.goal == "TEMP_FILE_CLEANUP"

        res14 = UniversalGoalResolver.resolve("System ko halka karne ke liye jo basic cleanup ho sakta hai, woh kar de.")
        assert res14.goal in ("SYSTEM_CLEANUP", "TEMP_FILE_CLEANUP")
        assert res14.decision in (ResolutionDecision.EXECUTE, ResolutionDecision.ASK_PRECISE_CLARIFICATION)

        res15 = UniversalGoalResolver.resolve("Mere kaam ka nahi hai jo temp data pada hai, use hata de.")
        assert res15.goal == "TEMP_FILE_CLEANUP"

        # 16-18: contextual repeat
        res16 = UniversalGoalResolver.resolve("Wahi cleanup ek baar aur kar dena.", context=ctx_temp)
        assert res16.goal == "TEMP_FILE_CLEANUP"
        assert res16.decision == ResolutionDecision.EXECUTE

        res17 = UniversalGoalResolver.resolve("Jo abhi kiya tha na, same cheez phir se kar.", context=ctx_temp)
        assert res17.goal == "TEMP_FILE_CLEANUP"
        assert res17.decision == ResolutionDecision.EXECUTE

        res18 = UniversalGoalResolver.resolve("Haan, wohi wala kaam repeat kar.", context=ctx_temp)
        assert res18.goal == "TEMP_FILE_CLEANUP"
        assert res18.decision == ResolutionDecision.EXECUTE

        # 19: complementary target ("Usko bhi saaf kar de" -> Recycle Bin after Temp)
        res19 = UniversalGoalResolver.resolve("Usko bhi saaf kar de.", context=ctx_temp)
        assert res19.goal == "RECYCLE_BIN_CLEANUP"
        assert res19.decision == ResolutionDecision.EXECUTE

        # 20: pronoun removal
        res20 = UniversalGoalResolver.resolve("Ye wala bhi hata de.", context=ctx_notepad)
        assert res20.goal == "CLOSE_APPLICATION"
        assert res20.entities.get("entity") == "notepad"

    # =========================================================================
    # Level 3 — Multi-turn Context Test (21-29)
    # =========================================================================
    def test_level_3_multi_turn_context(self):
        # Dialog 1: Chrome -> YouTube inside Chrome -> Close Chrome
        res21 = UniversalGoalResolver.resolve("Chrome kholo.")
        assert res21.goal == "OPEN_APPLICATION"
        assert res21.entities.get("entity") == "chrome"

        ctx_chrome = ActiveTargetContext()
        ctx_chrome.set_application("chrome")

        res22 = UniversalGoalResolver.resolve("Isme YouTube le aao.", context=ctx_chrome)
        assert res22.goal == "OPEN_WEBSITE"
        assert res22.entities.get("container") == "chrome"
        assert res22.entities.get("entity") == "youtube"

        res23 = UniversalGoalResolver.resolve("Ab isko band kar do.", context=ctx_chrome)
        assert res23.goal == "CLOSE_APPLICATION"
        assert res23.entities.get("entity") == "chrome"

        # Dialog 2: Temp files -> Dobara -> Ek baar aur wahi kar
        res24 = UniversalGoalResolver.resolve("Temp files clean kar do.")
        assert res24.goal == "TEMP_FILE_CLEANUP"

        ctx_temp = ActiveTargetContext()
        ctx_temp.update_command_context(intent="TEMP_FILE_CLEANUP", action="clear_temp_files", entities={"target": "temp_files"})

        res25 = UniversalGoalResolver.resolve("Dobara.", context=ctx_temp)
        assert res25.goal == "TEMP_FILE_CLEANUP"
        assert res25.decision == ResolutionDecision.EXECUTE

        res26 = UniversalGoalResolver.resolve("Ek baar aur wahi kar.", context=ctx_temp)
        assert res26.goal == "TEMP_FILE_CLEANUP"
        assert res26.decision == ResolutionDecision.EXECUTE

        # Dialog 3: Brave -> Gmail inside Brave -> Close Brave
        res27 = UniversalGoalResolver.resolve("Brave kholo.")
        assert res27.goal == "OPEN_APPLICATION"

        ctx_brave = ActiveTargetContext()
        ctx_brave.set_application("brave")

        res28 = UniversalGoalResolver.resolve("Isme Gmail khol do.", context=ctx_brave)
        assert res28.goal == "OPEN_WEBSITE"
        assert res28.entities.get("container") == "brave"

        res29 = UniversalGoalResolver.resolve("Ab isko close kar do.", context=ctx_brave)
        assert res29.goal == "CLOSE_APPLICATION"
        assert res29.entities.get("entity") == "brave"

    # =========================================================================
    # Level 4 — Indirect Meaning (30-39)
    # =========================================================================
    def test_level_4_indirect_meaning(self):
        res30 = UniversalGoalResolver.resolve("Computer mein jo unnecessary temporary cheezein jama hoti rehti hain, unko hata sakte ho?")
        assert res30.speech_act == "CAPABILITY_QUESTION"
        assert res30.goal == "TEMP_FILE_CLEANUP"
        assert res30.decision == ResolutionDecision.ANSWER

        res31 = UniversalGoalResolver.resolve("System ko thoda fresh kar do.")
        assert res31.goal == "SYSTEM_CLEANUP"

        res32 = UniversalGoalResolver.resolve("Machine se woh temporary garbage nikaal do.")
        assert res32.goal == "TEMP_FILE_CLEANUP"

        res33 = UniversalGoalResolver.resolve("Jo files bas jagah kha rahi hain aur temporary hain, unko clean kar.")
        assert res33.goal == "TEMP_FILE_CLEANUP"

        res34 = UniversalGoalResolver.resolve("Mujhe system ka basic cleanup chahiye.")
        assert res34.goal == "SYSTEM_CLEANUP"

        res35 = UniversalGoalResolver.resolve("Computer ko thoda tidy up kar de.")
        assert res35.goal == "SYSTEM_CLEANUP"

        res36 = UniversalGoalResolver.resolve("Disk par jo temporary maal pada hai usse saaf kar.")
        assert res36.goal == "TEMP_FILE_CLEANUP"

        res37 = UniversalGoalResolver.resolve("Jo recycle mein pada hai uska kya karna hai, hata de.")
        assert res37.goal == "RECYCLE_BIN_CLEANUP"

        res38 = UniversalGoalResolver.resolve("Mujhe woh browser chahiye jisme main usually web kholta hoon.")
        assert res38.goal == "OPEN_APPLICATION"
        assert res38.entities.get("entity") == "chrome"

        res39 = UniversalGoalResolver.resolve("Video wali site khol de.")
        assert res39.goal == "OPEN_WEBSITE"
        assert res39.entities.get("entity") == "youtube"

    # =========================================================================
    # Level 5 — Messy Human Speech (40-48)
    # =========================================================================
    def test_level_5_messy_human_speech(self):
        res40 = UniversalGoalResolver.resolve("Bhai zara jo temp wagairah pada hai na woh clean kar de please.")
        assert res40.goal == "TEMP_FILE_CLEANUP"

        res41 = UniversalGoalResolver.resolve("Arey woh temporary wala folder hai na, uska jo bhi unwanted hai hata.")
        assert res41.goal == "TEMP_FILE_CLEANUP"

        res42 = UniversalGoalResolver.resolve("Computer ko thoda saaf kar de yaar, especially jo temp type ka pada hai.")
        assert res42.goal == "TEMP_FILE_CLEANUP"

        res43 = UniversalGoalResolver.resolve("Chrome... haan wahi browser... usko chala de.")
        assert res43.goal == "OPEN_APPLICATION"
        assert res43.entities.get("entity") == "chrome"

        res44 = UniversalGoalResolver.resolve("Woh jo internet wala app hai usko open kar.")
        assert res44.goal == "OPEN_APPLICATION"
        assert res44.entities.get("entity") == "chrome"

        ctx_temp = ActiveTargetContext()
        ctx_temp.update_command_context(intent="TEMP_FILE_CLEANUP", action="clear_temp_files", entities={"target": "temp_files"})
        res45 = UniversalGoalResolver.resolve("Maine jo abhi bola tha usi ko repeat kar.", context=ctx_temp)
        assert res45.goal == "TEMP_FILE_CLEANUP"
        assert res45.decision == ResolutionDecision.EXECUTE

        ctx_chrome = ActiveTargetContext()
        ctx_chrome.set_application("chrome")
        res46 = UniversalGoalResolver.resolve("Nahi nahi, woh nahi, dusra wala.", context=ctx_chrome)
        assert res46.goal == "OPEN_APPLICATION"
        assert res46.entities.get("entity") == "brave"

        ctx_browser_yt = ActiveTargetContext()
        ctx_browser_yt.set_application("chrome")
        ctx_browser_yt.set_website("youtube")
        res47 = UniversalGoalResolver.resolve("Usi mein kholo.", context=ctx_browser_yt)
        assert res47.goal == "OPEN_WEBSITE"
        assert res47.entities.get("container") == "chrome"

        res48 = UniversalGoalResolver.resolve("Isko nahi, usko kar.")
        assert res48.decision == ResolutionDecision.ASK_PRECISE_CLARIFICATION

    # =========================================================================
    # Level 6 — Real Intelligence Test (50-59)
    # =========================================================================
    def test_level_6_real_intelligence(self):
        # 50: Negative constraint
        res50 = UniversalGoalResolver.resolve("Mujhe thoda system cleanup chahiye, lekin meri personal files ko touch mat karna.")
        assert res50.goal == "TEMP_FILE_CLEANUP"
        assert res50.parameters.get("exclude_personal_files") is True

        # 51: Specific conditional repeat
        ctx_temp = ActiveTargetContext()
        ctx_temp.update_command_context(intent="TEMP_FILE_CLEANUP", action="clear_temp_files", entities={"target": "temp_files"})
        res51 = UniversalGoalResolver.resolve("Jo kaam abhi kiya tha woh dobara kar, bas is baar wahi cheez jo temporary thi.", context=ctx_temp)
        assert res51.goal == "TEMP_FILE_CLEANUP"

        # 52: Negation in application selection
        res52 = UniversalGoalResolver.resolve("Browser kholna tha... haan, Brave nahi, doosra wala.")
        assert res52.goal == "OPEN_APPLICATION"
        assert res52.entities.get("entity") == "chrome"

        # 53: Active container inheritance
        ctx_active_app = ActiveTargetContext()
        ctx_active_app.set_application("chrome")
        res53 = UniversalGoalResolver.resolve("YouTube kholo, lekin browser khud choose karne ki zarurat nahi, jo main abhi use kar raha hoon usi mein.", context=ctx_active_app)
        assert res53.goal == "OPEN_WEBSITE"
        assert res53.entities.get("container") == "chrome"

        # 54: Negative constraint
        res54 = UniversalGoalResolver.resolve("Jo unnecessary temporary stuff hai use hata de, lekin jo user files hain woh rehne de.")
        assert res54.goal == "TEMP_FILE_CLEANUP"
        assert res54.parameters.get("exclude_personal_files") is True

        # 55: Second part repeat
        res55 = UniversalGoalResolver.resolve("Pichhle command ka jo second part tha, bas wahi repeat kar.", context=ctx_temp)
        assert res55.goal == "TEMP_FILE_CLEANUP"

        # 56: Conversational repair
        res56 = UniversalGoalResolver.resolve("Nahi, jo tumne samjha woh nahi; mera matlab temp cleanup se tha.")
        assert res56.goal == "TEMP_FILE_CLEANUP"

        # 57: Negation scoping on Recycle Bin
        res57 = UniversalGoalResolver.resolve("Computer ko clean karna hai, par Recycle Bin ko abhi chhod do.")
        assert res57.goal == "TEMP_FILE_CLEANUP"
        assert res57.decision == ResolutionDecision.EXECUTE

        # 58: Sequential multi-intent
        res58 = UniversalGoalResolver.resolve("Pehle browser kholo, phir usi ke andar video wali website chala dena.")
        assert res58.goal == "OPEN_WEBSITE"
        assert res58.entities.get("container") == "chrome"
        assert res58.entities.get("entity") == "youtube"

        # 59: Meta-contextual inference
        res59 = UniversalGoalResolver.resolve("Main command exact nahi bolunga, tum context se samajhne ki koshish karo ki mujhe kya chahiye.", context=ctx_active_app)
        assert res59.goal == "META_CONTEXTUAL_ASSISTANCE"
        assert res59.decision == ResolutionDecision.ANSWER

    # =========================================================================
    # Sabse Hard 10 (60-69)
    # =========================================================================
    def test_sabse_hard_10(self):
        ctx_clean = ActiveTargetContext()
        ctx_clean.update_command_context(intent="TEMP_FILE_CLEANUP", action="clear_temp_files", entities={"target": "temp_files"})

        ctx_chrome = ActiveTargetContext()
        ctx_chrome.set_application("chrome")
        ctx_chrome.update_command_context(intent="OPEN_APPLICATION", action="launch_app", entities={"entity": "chrome"})

        # 60
        res60 = UniversalGoalResolver.resolve("Bhai jo cheez abhi clean ki thi usmein se temporary wali dobara nikaal de.", context=ctx_clean)
        assert res60.goal == "TEMP_FILE_CLEANUP"
        assert res60.decision == ResolutionDecision.EXECUTE

        # 61
        res61 = UniversalGoalResolver.resolve("System ko halka karna hai, woh basic wala kaam kar.")
        assert res61.goal in ("SYSTEM_CLEANUP", "TEMP_FILE_CLEANUP")

        # 62
        res62 = UniversalGoalResolver.resolve("Wahi app kholo jisme kal maine video chalayi thi.")
        assert res62.goal == "OPEN_APPLICATION"
        assert res62.entities.get("entity") in ("vlc", "youtube")

        # 63
        res63 = UniversalGoalResolver.resolve("Isko nahi, jo doosra browser hai usmein kholo.", context=ctx_chrome)
        assert res63.goal == "OPEN_APPLICATION"
        assert res63.entities.get("entity") == "brave"

        # 64: Inverse action
        res64 = UniversalGoalResolver.resolve("Jo pichhli baar kiya tha, uska ulta kar.", context=ctx_chrome)
        assert res64.goal == "CLOSE_APPLICATION"
        assert res64.entities.get("app_name") == "chrome"

        # 65: Context repeat
        res65 = UniversalGoalResolver.resolve("Pehle wala kaam rehne de, baad mein jo kiya tha woh kar.", context=ctx_clean)
        assert res65.goal == "TEMP_FILE_CLEANUP"

        # 66: Contrastive negation
        res66 = UniversalGoalResolver.resolve("Temporary nahi, recycle wala hata dena.")
        assert res66.goal == "RECYCLE_BIN_CLEANUP"
        assert res66.decision == ResolutionDecision.EXECUTE

        # 67: Safety constraint
        res67 = UniversalGoalResolver.resolve("Computer clean kar do, lekin woh wali jagah mat chhedna jahan meri files hain.")
        assert res67.goal == "TEMP_FILE_CLEANUP"
        assert res67.parameters.get("exclude_personal_files") is True

        # 68 & 69: Meta-contextual assistance
        res68 = UniversalGoalResolver.resolve("Mujhe exact command yaad nahi hai, kaam tum context se samajh lo.", context=ctx_chrome)
        assert res68.goal == "META_CONTEXTUAL_ASSISTANCE"

        res69 = UniversalGoalResolver.resolve("Main kaise bolun ye mat dekho; samjho main karna kya chahta hoon.", context=ctx_chrome)
        assert res69.goal == "META_CONTEXTUAL_ASSISTANCE"
