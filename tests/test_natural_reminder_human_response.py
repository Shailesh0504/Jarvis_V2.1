# tests/test_natural_reminder_human_response.py
"""
Test suite validating human-like understanding and conversational 2nd-person response
for natural Hindi / Hinglish reminders:
  1. Natural relative time understanding: '5 minut baad mujhe yaad dilana ki mujhe paani pina hai'
  2. Follow-up duration understanding: '5 minut baad'
  3. Clean task extraction without 1st-person pronouns ('mujhe paani pina' -> 'paani peene')
  4. Natural, human-like reminder alert formatting with Hindi oblique infinitive inflections:
     'Boss, aapke paani peene ka time ho gaya hai.' instead of mechanical 'Mujhe paani pina ka time ho gaya hai'
"""

import pytest
from core.conversational_intent import (
    ConversationalIntentClassifier,
    ConversationalIntentType
)
from core.dialog_manager import DialogManager
from plugins.reminder.plugin import format_reminder_alert


def test_relative_time_and_task_extraction_5_minut_baad():
    """Validates full understanding of '5 minut baad mujhe yaad dilana ki mujhe paani pina hai'."""
    text = "5 minut baad mujhe yaad dilana ki mujhe paani pina hai"
    res = ConversationalIntentClassifier.classify(text)

    # 1. Intent should be ACTION_COMMAND for CREATE_REMINDER
    assert res.intent_type == ConversationalIntentType.ACTION_COMMAND
    assert res.action_type == "create_reminder"
    assert res.is_executable is True

    # 2. Time must be parsed into datetime and display string (+5 mins from now)
    assert res.parameters.get("datetime") is not None
    assert res.parameters.get("iso_time") is not None
    assert "5 minute baad" in (res.parameters.get("time_display") or "")

    # 3. Task description must be clean without 1st-person 'mujhe'
    task = res.parameters.get("description") or ""
    assert "mujhe" not in task.lower()
    assert "paani peene" in task.lower() or "paani pina" in task.lower()


def test_dialog_manager_parses_5_minut_baad():
    """Validates DialogManager parses '5 minut baad' as a relative delay rather than failing."""
    iso, disp = DialogManager._parse_compose_time("5 minut baad")
    assert iso is not None
    assert disp is not None
    assert "5" in disp


def test_format_reminder_alert_human_response():
    """Validates human-like 2nd person phrasing and proper Hindi grammar inflections."""
    # 1. User's exact case: 'Mujhe paani pina'
    alert_spoken = format_reminder_alert("Mujhe paani pina", is_missed=False, for_spoken=True)
    alert_display = format_reminder_alert("Mujhe paani pina", is_missed=False, for_spoken=False)
    assert alert_spoken == "Boss, aapke paani peene ka time ho gaya hai."
    assert alert_display == "⏰ Reminder: Boss, aapke paani peene ka time ho gaya hai!"

    # 2. 'paani peene'
    alert2 = format_reminder_alert("paani peene", is_missed=False, for_spoken=True)
    assert alert2 == "Boss, aapke paani peene ka time ho gaya hai."

    # 3. 'dawai leni hai' (feminine noun -> 'aapki')
    alert3 = format_reminder_alert("dawai leni hai", is_missed=False, for_spoken=True)
    assert alert3 == "Boss, aapki dawai lene ka time ho gaya hai."

    # 4. 'gym jaana'
    alert4 = format_reminder_alert("gym jaana", is_missed=False, for_spoken=True)
    assert alert4 == "Boss, aapke gym jaane ka time ho gaya hai."

    # 5. 'Meeting' (feminine noun)
    alert5 = format_reminder_alert("Meeting", is_missed=False, for_spoken=True)
    assert alert5 == "Boss, aapki Meeting ka time ho gaya hai."

    # 6. 'Sone ka time ho gaya hai' (never duplicate 'ka time ho gaya hai')
    alert6 = format_reminder_alert("Sone ka time ho gaya hai", is_missed=False, for_spoken=True)
    assert alert6 == "Boss, aapke Sone ka time ho gaya hai."
    assert "ka time ho gaya hai ka time ho gaya hai" not in alert6

    # 7. Missed reminder
    alert7 = format_reminder_alert("paani peene", is_missed=True, for_spoken=True)
    assert alert7 == "Boss, aapka ek reminder miss ho gaya tha: paani peene."
