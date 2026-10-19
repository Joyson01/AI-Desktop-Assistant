import json

from PIL import Image

from brain.providers.grok_visual_brain import GrokVisualBrain
from scripts import smoke_grok_visual_brain


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


def test_dry_run_prepares_screenshot_without_request(capsys):
    calls = []

    def capture():
        calls.append("capture")
        return Image.new("RGB", (20, 10))

    assert smoke_grok_visual_brain.main(["--dry-run"], capture=capture, environ={}) == 0
    output = capsys.readouterr().out

    assert calls == ["capture"]
    assert "no Grok request" in output
    assert "configured=False" in output


def test_guard_prevents_request_without_opt_in(monkeypatch, capsys):
    monkeypatch.delenv("RUN_REAL_GROK_SMOKE", raising=False)
    requests = []

    class UnexpectedBrain:
        def __init__(self, **kwargs):
            requests.append(kwargs)

    assert smoke_grok_visual_brain.main([], capture=lambda: object(), brain_factory=UnexpectedBrain, environ={"XAI_API_KEY": "secret"}) == 0
    assert requests == []
    assert "disabled" in capsys.readouterr().out


def test_missing_key_does_not_capture_or_request_when_opted_in(capsys):
    calls = []

    assert smoke_grok_visual_brain.main([], capture=lambda: calls.append("capture"), environ={"RUN_REAL_GROK_SMOKE": "1"}) == 0
    assert calls == []
    assert "not configured" in capsys.readouterr().out


def test_opted_in_smoke_uses_one_fake_request_and_never_executes():
    transport = FakeTransport(json.dumps({"action": "done", "message": "Complete", "confidence": 1.0}))
    created = []

    def factory(**kwargs):
        created.append(kwargs)
        return GrokVisualBrain(transport=transport, model=kwargs["model"])

    output = []
    result = smoke_grok_visual_brain.main(
        [],
        capture=lambda: Image.new("RGB", (20, 10)),
        brain_factory=factory,
        environ={"XAI_API_KEY": "secret", "XAI_MODEL": "grok-test", "RUN_REAL_GROK_SMOKE": "1"},
    )
    assert result == 0
    assert len(transport.calls) == 1
    assert created == [{"api_key": "secret", "model": "grok-test"}]
    assert output == []


def test_opted_in_smoke_reports_provider_failure_without_secret(capsys):
    class FailingBrain:
        def __init__(self, **kwargs):
            pass

        def analyze(self, brain_input):
            raise TimeoutError("secret should not be printed")

    smoke_grok_visual_brain.main(
        [],
        capture=lambda: Image.new("RGB", (20, 10)),
        brain_factory=FailingBrain,
        environ={"XAI_API_KEY": "secret", "RUN_REAL_GROK_SMOKE": "1"},
    )
    output = capsys.readouterr().out
    assert "request=failed error=TimeoutError" in output
    assert "secret" not in output