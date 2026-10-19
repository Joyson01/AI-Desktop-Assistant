"""Quick integration test for Memory and SmartBrain with assistant.py"""
from assistant import AccessibilityAssistant

def test_integration():
    # Test initialization
    assistant = AccessibilityAssistant(dry_run=True)

    # Verify memory and smart_brain are initialized
    assert assistant.memory is not None, "memory not initialized"
    assert assistant.smart_brain is not None, "smart_brain not initialized"

    # Test memory methods
    assistant.memory.remember_goal("test goal")
    assert assistant.memory.last_goal == "test goal", "remember_goal failed"

    # Test smart_brain routing (without executing)
    decision = assistant.smart_brain.decide("hello", assistant.memory)
    assert decision.mode == "conversation", f"Expected 'conversation', got '{decision.mode}'"

    decision = assistant.smart_brain.decide("scroll down", assistant.memory)
    assert decision.mode == "fast_local", f"Expected 'fast_local', got '{decision.mode}'"

    decision = assistant.smart_brain.decide("YouTube kholo", assistant.memory)
    assert decision.mode in {"web_navigation", "web_media"}, f"Expected 'web_navigation' or 'web_media', got '{decision.mode}'"

    print("✓ All integration tests passed!")
    print(f"  - Memory initialized and functional")
    print(f"  - SmartBrain initialized and functional")
    print(f"  - Routing decisions working correctly")

if __name__ == "__main__":
    test_integration()
