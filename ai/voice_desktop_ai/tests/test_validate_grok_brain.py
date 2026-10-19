import json

from PIL import Image

from brain.providers.grok_visual_brain import GrokVisualBrain
from scripts import validate_grok_brain


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    class Responses:
        def __init__(self, owner):
            self.owner = owner

        def create(self, **kwargs):
            self.owner.calls.append(kwargs)
            return {"output_text": self.owner.response}

    @property
    def responses(self):
        return self.Responses(self)


def run_fake(scenario, payload, capsys):
    transport = FakeTransport(json.dumps(payload))

    def factory(**kwargs):
        return GrokVisualBrain(transport=transport, model=kwargs["model"])

    code = validate_grok_brain.main(
        ["--scenario", scenario, "--real"],
        capture=lambda: Image.new("RGB", (800, 600)),
        brain_factory=factory,
        environ={"XAI_API_KEY": "secret", "XAI_MODEL": "grok-test", "RUN_REAL_GROK_SMOKE": "1"},
    )
    return code, transport.calls, capsys.readouterr().out


def test_all_scenarios_send_one_screenshot_request_and_report_one_action(capsys):
    for scenario in validate_grok_brain.SCENARIOS:
        code, calls, output = run_fake(scenario, {"action": "done", "message": "Complete"}, capsys)

        assert code == 0
        assert len(calls) == 1
        assert calls[0]["input"][1]["content"][1]["type"] == "input_image"
        assert "action_executed=no" in output
        assert "secret" not in output


def test_guard_prevents_real_request(capsys):
    calls = []

    class UnexpectedBrain:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    validate_grok_brain.main(
        ["--scenario", "open_chrome", "--real"],
        capture=lambda: object(),
        brain_factory=UnexpectedBrain,
        environ={"XAI_API_KEY": "secret", "RUN_REAL_GROK_SMOKE": "0"},
    )

    assert calls == []
    assert "disabled" in capsys.readouterr().out


def test_invalid_response_is_safe_ask_user_and_never_executor(capsys):
    _, calls, output = run_fake("enter_button", {"action": "delete_everything"}, capsys)

    assert len(calls) == 1
    assert "action_type=ask_user" in output
    assert "action_executed=no" in output


def test_ambiguous_and_done_results_are_safe(capsys):
    for payload, action in (
        ({"action": "ask_user", "message": "Which YouTube target?"}, "ask_user"),
        ({"action": "done", "message": "Finished"}, "done"),
    ):
        _, _, output = run_fake("account_search_play", payload, capsys)
        assert f"action_type={action}" in output
        assert "action_executed=no" in output


def test_diagnostic_mode_reports_safe_metadata(capsys):
    transport = FakeTransport(json.dumps({"action": "done", "message": "Complete"}))

    def factory(**kwargs):
        return GrokVisualBrain(transport=transport, model=kwargs["model"])

    validate_grok_brain.main(
        ["--scenario", "open_chrome", "--real", "--diagnostic"],
        capture=lambda: Image.new("RGB", (800, 600)),
        brain_factory=factory,
        environ={"XAI_API_KEY": "secret", "XAI_MODEL": "grok-test", "RUN_REAL_GROK_SMOKE": "1"},
    )
    output = capsys.readouterr().out
    assert "diagnostic_screenshot_width=800" in output
    assert "diagnostic_image_mime_type=image/png" in output
    assert "diagnostic_image_byte_length=" in output
    assert "diagnostic_request_contains_image=True" in output
    assert "secret" not in output


def test_debug_mode_reports_redacted_request_contract_without_provider_call(capsys):
    calls = []

    class DebugBrain(GrokVisualBrain):
        def debug_request(self, brain_input):
            calls.append("debug")
            return {"endpoint": "https://api.x.ai/v1/responses", "image_mime_type": "image/png", "image_byte_length": 10}

    validate_grok_brain.main(
        ["--scenario", "open_chrome", "--debug"],
        capture=lambda: Image.new("RGB", (800, 600)),
        brain_factory=DebugBrain,
        environ={"XAI_API_KEY": "secret", "XAI_MODEL": "grok-test", "RUN_REAL_GROK_SMOKE": "1"},
    )
    output = capsys.readouterr().out
    assert calls == ["debug"]
    assert "debug_endpoint=https://api.x.ai/v1/responses" in output
    assert "debug_image_mime_type=image/png" in output
    assert "secret" not in output