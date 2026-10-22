# tests/test_event_bus.py
import pytest
from core.event_bus import EventBus, Event


def test_event_bus_exact_subscribe_and_publish():
    bus = EventBus()
    received = []

    def handler(evt: Event):
        received.append(evt.data)

    bus.subscribe("user.login", handler)
    bus.emit("user.login", data={"user": "Boss"})

    assert len(received) == 1
    assert received[0]["user"] == "Boss"


def test_event_bus_wildcard():
    bus = EventBus()
    events = []

    def wildcard_handler(evt: Event):
        events.append(evt.topic)

    bus.subscribe("executor.*", wildcard_handler)

    bus.emit("executor.step_start", data={})
    bus.emit("executor.step_end", data={})
    bus.emit("input.received", data={})

    assert events == ["executor.step_start", "executor.step_end"]


def test_event_bus_unsubscribe():
    bus = EventBus()
    counter = [0]

    def handler(evt: Event):
        counter[0] += 1

    bus.subscribe("test.topic", handler)
    bus.emit("test.topic")
    assert counter[0] == 1

    bus.unsubscribe("test.topic", handler)
    bus.emit("test.topic")
    assert counter[0] == 1
