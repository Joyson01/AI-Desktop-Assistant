from types import SimpleNamespace

from actions.engine import execute
from brain.intent import Intent


def test_click_refreshes_and_verifies_after_invocation():
    calls = []
    after = SimpleNamespace(ui_elements=[])

    result = execute(
        Intent("click", target="Images"),
        before=None,
        refresh=lambda: calls.append("refresh") or after,
        resolve=lambda target, role: calls.append(("resolve", target)) or object(),
        invoke=lambda element, action: calls.append(("invoke", action)) or True,
    )

    assert result.success is True
    assert result.verified is True
    assert calls == [("resolve", "Images"), ("invoke", "click"), "refresh"]


def test_click_is_not_verified_when_post_click_observation_is_invalid():
    result = execute(
        Intent("click", target="Images"),
        before=None,
        refresh=lambda: None,
        resolve=lambda target, role: object(),
        invoke=lambda element, action: True,
    )

    assert result.success is True
    assert result.verified is False


def test_click_returns_failure_when_real_click_function_fails():
    result = execute(
        Intent("click", target="money"),
        before=None,
        refresh=lambda: SimpleNamespace(ui_elements=[]),
        resolve=lambda target, role: object(),
        invoke=lambda element, action: False,
    )

    assert result.success is False
    assert result.verified is False
    assert result.message == "click function failed"


def test_dry_run_does_not_invoke_real_click():
    invoked = []
    result = execute(
        Intent("click", target="money"),
        before=None,
        refresh=lambda: SimpleNamespace(ui_elements=[]),
        resolve=lambda target, role: object(),
        invoke=lambda element, action: invoked.append(True),
        dry_run=True,
    )

    assert result.success is True
    assert result.verified is True
    assert invoked == []


def test_click_uses_pre_resolved_element_without_resolving_again():
    calls = []
    element = object()
    result = execute(
        Intent("click", target="Settings"),
        before=SimpleNamespace(ui_elements=[]),
        refresh=lambda: SimpleNamespace(ui_elements=[]),
        resolve=lambda target, role: calls.append("resolve") or object(),
        invoke=lambda target, action: calls.append((target, action)) or True,
        resolved_element=element,
    )

    assert result.success is True
    assert calls == [(element, "click")]