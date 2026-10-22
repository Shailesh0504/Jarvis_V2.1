# tests/test_settings_combos.py
"""Settings Appearance combos: pretty display text, raw snake_case values,
readable popup list (no dark-on-dark dropdown)."""

import pytest
from PySide6.QtWidgets import QApplication

from gui.island.views import CoucouSettingsCard

app = QApplication.instance() or QApplication(["-platform", "offscreen"])


@pytest.fixture()
def card():
    c = CoucouSettingsCard()
    yield c
    c.close()


def test_accessory_pretty_text_raw_value(card):
    texts = [card.accessory_combo.itemText(i) for i in range(card.accessory_combo.count())]
    assert "Santa Hat" in texts
    assert "Round Glasses" in texts
    assert "santa_hat" not in texts  # raw values never shown
    values = [card.accessory_combo.itemData(i) for i in range(card.accessory_combo.count())]
    assert "santa_hat" in values
    assert "round_glasses" in values


def test_combo_signals_emit_raw_values(card):
    got = []
    card.accessory_changed.connect(got.append)
    idx = [card.accessory_combo.itemData(i) for i in range(card.accessory_combo.count())].index("witch_hat")
    card.accessory_combo.setCurrentIndex(idx)
    assert got == ["witch_hat"]

    got2 = []
    card.animation_changed.connect(got2.append)
    card.anim_combo.setCurrentIndex(0)
    assert got2 == ["calm"]

    got3 = []
    card.theme_changed.connect(got3.append)
    card.theme_combo.setCurrentIndex(1)
    assert got3 == ["darker"]


def test_anim_defaults_to_normal(card):
    assert card.anim_combo.currentData() == "normal"


def test_popup_list_is_readable(card):
    for combo in (card.accessory_combo, card.anim_combo, card.theme_combo):
        ss = combo.styleSheet()
        assert "QAbstractItemView" in ss
        assert "selection-background-color" in ss
        assert combo.view().minimumWidth() >= 140


def test_combo_selection_reaches_character_outfit():
    """Pretty 'Santa Hat' click → raw 'santa_hat' lands on the character."""
    from gui.island.island import CoucouIslandWidget
    island = CoucouIslandWidget()
    try:
        combo = island.view_settings.accessory_combo
        idx = [combo.itemData(i) for i in range(combo.count())].index("santa_hat")
        combo.setCurrentIndex(idx)
        assert island.character.accessories.current.value == "santa_hat"
    finally:
        island.view_settings.accessory_combo.setCurrentIndex(0)
        island.close()
