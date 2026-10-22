# tests/test_model_gateway_and_health.py
import pytest
from core.models import (
    ModelGateway,
    LLMProvider,
    STTProvider,
    TTSProvider,
    DefaultLocalLLMAdapter,
    DefaultLocalSTTAdapter,
    DefaultLocalTTSAdapter,
)
from core.observability import HealthMonitor, HealthStatus


class DummyLLM(LLMProvider):
    def generate(self, prompt: str, system_prompt=None, **kwargs) -> str:
        return f"Echo: {prompt}"

    def chat(self, messages, **kwargs) -> str:
        return "Chat response"


def test_model_gateway_registration():
    gw = ModelGateway()
    assert isinstance(gw.llm, LLMProvider)
    assert isinstance(gw.stt, STTProvider)
    assert isinstance(gw.tts, TTSProvider)

    dummy = DummyLLM()
    gw.register_llm(dummy)
    assert gw.llm.generate("Hello") == "Echo: Hello"


def test_health_monitor_component_tracking():
    hm = HealthMonitor()
    summary = hm.get_system_summary()
    assert summary["overall_status"] == "HEALTHY"
    assert "stt" in summary["components"]
    assert "tts" in summary["components"]

    # Degrade a non-critical component (e.g. plugins)
    hm.record_status("plugins", HealthStatus.DEGRADED, details="1 plugin failed to load")
    summary = hm.get_system_summary()
    assert summary["overall_status"] == "DEGRADED"
    assert summary["components"]["plugins"]["status"] == "DEGRADED"

    # Restore to healthy
    hm.record_status("plugins", HealthStatus.HEALTHY, details="All plugins loaded")
    summary = hm.get_system_summary()
    assert summary["overall_status"] == "HEALTHY"


def test_health_monitor_checker_execution():
    hm = HealthMonitor()
    hm.register_checker("database", lambda: (HealthStatus.HEALTHY, "WAL mode active"))
    hm.run_health_checks()
    summary = hm.get_system_summary()
    assert summary["components"]["database"]["status"] == "HEALTHY"
    assert "WAL mode active" in summary["components"]["database"]["details"]
