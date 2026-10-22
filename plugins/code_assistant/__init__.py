# plugins/code_assistant/__init__.py
"""Code Assistant Plugin package for Jarvis V2.1."""

from .plugin import CodeAssistantPlugin
from .models import AssistantMode

__all__ = ["CodeAssistantPlugin", "AssistantMode"]
