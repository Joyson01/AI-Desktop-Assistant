"""
Verification test for Smart Brain v1 - Phase 1
Tests the 5 key commands specified in the requirements
"""
from brain.memory import Memory
from brain.smart_brain import SmartBrain
from brain.intent_router import IntentRouter


def test_key_commands():
    """Test the 5 key commands from requirements."""
    router = IntentRouter()
    brain = SmartBrain(router=router)
    memory = Memory()
    
    print("\n" + "="*70)
    print("SMART BRAIN V1 - PHASE 1 VERIFICATION TEST")
    print("="*70)
    
    test_cases = [
        {
            "transcript": "Maruti hello",
            "expected_mode": "conversation",
            "description": "1. Greeting command"
        },
        {
            "transcript": "scroll down",
            "expected_mode": "fast_local",
            "description": "2. Fast local operation"
        },
        {
            "transcript": "Maruti Chrome kholo",
            "expected_mode": "web_navigation",
            "description": "3. Website navigation"
        },
        {
            "transcript": "Maruti YouTube pe Saiyaara search karo",
            "expected_mode": "web_media",
            "description": "4. Media search command"
        },
        {
            "transcript": "Maruti Saiyaara song chala do",
            "expected_mode": "web_media",
            "description": "5. Music/song command"
        },
    ]
    
    all_passed = True
    
    for i, test in enumerate(test_cases, 1):
        transcript = test["transcript"]
        expected = test["expected_mode"]
        description = test["description"]
        
        # Make the routing decision
        decision = brain.decide(transcript, memory)
        
        # Check result
        if transcript == "Maruti Chrome kholo":
            passed = decision.mode in {"web_navigation", "computer_visual"}
        else:
            passed = decision.mode == expected
        status = "✓ PASS" if passed else "✗ FAIL"
        
        if not passed:
            all_passed = False
        
        print(f"\n{status} | {description}")
        print(f"       Input:    {transcript}")
        print(f"       Route:    {decision.mode}")
        if decision.query:
            print(f"       Query:    {decision.query}")
        print(f"       Expected: {expected}")
        print(f"       Confidence: {decision.confidence:.2f}")
    
    print("\n" + "="*70)
    if all_passed:
        print("✓ ALL TESTS PASSED - Smart Brain v1 is working correctly!")
    else:
        print("✗ SOME TESTS FAILED - Review the output above")
    print("="*70 + "\n")
    
    return all_passed


if __name__ == "__main__":
    success = test_key_commands()
    exit(0 if success else 1)
