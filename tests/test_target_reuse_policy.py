# tests/test_target_reuse_policy.py
import pytest
from unittest.mock import patch, MagicMock
from core.app import JarvisCore
from brain.semantic_parser import HinglishNLUParser
from core.target_engine import TargetCandidate, TargetKind, TargetRequest


@pytest.fixture
def jarvis_core():
    return JarvisCore()


def test_nlu_parses_new_tab_modifier():
    """
    Verifies that 'Flipkart ka naya tab kholo' and 'YouTube naye tab mein kholo'
    set force_new=True, while 'Flipkart open karo' defaults to force_new=False.
    """
    # 1. Default (reuse existing if open)
    act1 = HinglishNLUParser.parse("Flipkart open karo")
    assert act1 is not None
    assert act1.parameters.get("force_new") is False or act1.parameters.get("force_new") is None

    # 2. Explicit new tab on Flipkart
    act2 = HinglishNLUParser.parse("Flipkart ka naya tab kholo")
    assert act2 is not None
    assert act2.parameters.get("force_new") is True
    assert act2.parameters.get("site") == "flipkart"

    # 3. Explicit new tab on YouTube
    act3 = HinglishNLUParser.parse("YouTube ka naya tab kholo")
    assert act3 is not None
    assert act3.parameters.get("force_new") is True

    # 4. Explicit new tab on Amazon
    act4 = HinglishNLUParser.parse("Amazon naye tab mein kholo")
    assert act4 is not None
    assert act4.parameters.get("force_new") is True
    assert act4.parameters.get("site") == "amazon"

    # 5. Explicit new tab on Dhan
    act5 = HinglishNLUParser.parse("open new tab of dhan")
    assert act5 is not None
    assert act5.parameters.get("force_new") is True


def test_flipkart_open_reuses_existing_tab_when_already_open(jarvis_core):
    """
    When user says 'Flipkart open karo' and a Flipkart tab is already open in Brave,
    Jarvis activates that tab and DOES NOT open a new browser tab or URL.
    """
    flipkart_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="102",
        title="Online Shopping Site for Mobiles, Electronics, Furniture - Flipkart",
        url="https://www.flipkart.com/",
        browser="brave",
        confidence=1.0,
    )

    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[flipkart_tab]), \
         patch.object(jarvis_core.target_engine.tab_manager, "perform_tab_action", return_value=True) as mock_tab_action, \
         patch("webbrowser.open") as mock_web_open, \
         patch("webbrowser.open_new_tab") as mock_web_new_tab:

        resp = jarvis_core.process_input("Flipkart open karo")
        assert "Flipkart" in resp or "flipkart" in resp
        assert "active kar diya" in resp
        mock_tab_action.assert_called_once_with("activate_tab", flipkart_tab)
        mock_web_open.assert_not_called()
        mock_web_new_tab.assert_not_called()


def test_flipkart_open_opens_new_tab_when_not_already_open(jarvis_core):
    """
    When user says 'Flipkart open karo' and Flipkart is NOT open anywhere,
    Jarvis opens Flipkart in the browser.
    """
    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[]), \
         patch("plugins.browser.plugin.webbrowser.open", return_value=True) as mock_web_open:

        resp = jarvis_core.process_input("Flipkart open karo")
        assert "Flipkart" in resp or "flipkart" in resp
        mock_web_open.assert_called_once()
        assert "flipkart.com" in mock_web_open.call_args[0][0]


def test_flipkart_ka_naya_tab_kholo_forces_new_tab_even_if_open(jarvis_core):
    """
    When user says 'Flipkart ka naya tab kholo', Jarvis forces opening a new tab
    even if a Flipkart tab already exists.
    """
    flipkart_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="102",
        title="Flipkart",
        url="https://www.flipkart.com/",
        browser="brave",
        confidence=1.0,
    )

    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[flipkart_tab]), \
         patch("plugins.browser.plugin.webbrowser.open_new_tab", return_value=True) as mock_web_new_tab:

        resp = jarvis_core.process_input("Flipkart ka naya tab kholo")
        assert "Flipkart" in resp or "flipkart" in resp
        assert "naye tab mein open" in resp
        mock_web_new_tab.assert_called_once()
        assert "flipkart.com" in mock_web_new_tab.call_args[0][0]


def test_youtube_open_reuses_existing_tab_when_open(jarvis_core):
    """
    When user says 'YouTube open karo' and YouTube tab is already open,
    Jarvis activates that tab instead of opening a duplicate tab.
    """
    youtube_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="201",
        title="YouTube",
        url="https://www.youtube.com/",
        browser="chrome",
        confidence=1.0,
    )

    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[youtube_tab]), \
         patch.object(jarvis_core.target_engine.tab_manager, "perform_tab_action", return_value=True) as mock_tab_action, \
         patch("plugins.browser.plugin.webbrowser.open") as mock_web_open:

        resp = jarvis_core.process_input("YouTube open karo")
        assert "youtube" in resp.lower()
        assert "active kar diya" in resp
        mock_tab_action.assert_called_once_with("activate_tab", youtube_tab)
        mock_web_open.assert_not_called()


def test_youtube_ka_naya_tab_kholo_forces_new_tab(jarvis_core):
    """
    When user says 'YouTube ka naya tab kholo', Jarvis forces a new tab.
    """
    with patch("plugins.browser.plugin.webbrowser.open_new_tab", return_value=True) as mock_web_new_tab:
        resp = jarvis_core.process_input("YouTube ka naya tab kholo")
        assert "youtube" in resp.lower()
        assert "naye tab mein open" in resp
        mock_web_new_tab.assert_called_once()


def test_gmail_reuse_vs_new_tab(jarvis_core):
    """
    When user says 'Gmail open karo' with Gmail already open, activates tab;
    with 'Gmail ka naya tab kholo', opens a new tab.
    """
    gmail_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="301",
        title="Inbox - user@gmail.com - Gmail",
        url="https://mail.google.com/",
        browser="edge",
        confidence=1.0,
    )

    # 1. Reuse existing
    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[gmail_tab]), \
         patch.object(jarvis_core.target_engine.tab_manager, "perform_tab_action", return_value=True) as mock_tab_action, \
         patch("plugins.browser.plugin.webbrowser.open") as mock_web_open:

        resp = jarvis_core.process_input("Gmail open karo")
        assert "gmail" in resp.lower()
        assert "active kar diya" in resp
        mock_tab_action.assert_called_once_with("activate_tab", gmail_tab)
        mock_web_open.assert_not_called()

    # 2. Force new
    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[gmail_tab]), \
         patch("plugins.browser.plugin.webbrowser.open_new_tab", return_value=True) as mock_web_new_tab:

        resp = jarvis_core.process_input("Gmail ka naya tab kholo")
        assert "gmail" in resp.lower()
        assert "naye tab mein open" in resp
        mock_web_new_tab.assert_called_once()


def test_github_and_amazon_reuse_vs_new_tab(jarvis_core):
    """
    Verifies universality for GitHub and Amazon.
    """
    github_tab = TargetCandidate(
        kind=TargetKind.BROWSER_TAB,
        identity="401",
        title="GitHub Dashboard",
        url="https://github.com/",
        browser="brave",
        confidence=1.0,
    )

    # GitHub reuse
    with patch.object(jarvis_core.target_engine.resolver, "resolve", return_value=[github_tab]), \
         patch.object(jarvis_core.target_engine.tab_manager, "perform_tab_action", return_value=True) as mock_tab_action, \
         patch("plugins.browser.plugin.webbrowser.open") as mock_web_open:

        resp = jarvis_core.process_input("GitHub kholo")
        assert "github" in resp.lower()
        assert "active kar diya" in resp
        mock_tab_action.assert_called_once_with("activate_tab", github_tab)
        mock_web_open.assert_not_called()

    # Amazon force new tab
    with patch("plugins.browser.plugin.webbrowser.open_new_tab", return_value=True) as mock_web_new_tab:
        resp = jarvis_core.process_input("Amazon ka naya tab kholo")
        assert "amazon" in resp.lower()
        assert "naye tab mein open" in resp
        mock_web_new_tab.assert_called_once()
