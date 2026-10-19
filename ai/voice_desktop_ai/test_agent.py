"""Basic integration smoke test for assistant agent."""
from assistant import AccessibilityAssistant


def test_agent_initialization():
    agent = AccessibilityAssistant(dry_run=True)
    assert agent is not None
    assert agent.dry_run is True


if __name__ == "__main__":
    test_agent_initialization()
    print("✓ test_agent passed")

