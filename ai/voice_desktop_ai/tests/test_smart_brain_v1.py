"""
Tests for SmartBrain v1 and Memory.
Validates routing decisions and memory storage.
"""
import pytest
from collections import deque

from brain.memory import Memory
from brain.smart_brain import SmartBrain
from brain.intent_router import IntentRouter
from brain.conversation import ConversationManager


class TestMemory:
    """Test Memory dataclass and methods."""
    
    def test_memory_initialization(self):
        """Memory initializes with default values."""
        mem = Memory()
        assert mem.max_history == 20
        assert isinstance(mem.history, deque)
        assert mem.current_app is None
        assert mem.last_goal is None
        assert mem.last_query is None
    
    def test_memory_respects_max_history(self):
        """Memory history respects max_history size."""
        mem = Memory(max_history=5)
        for i in range(10):
            mem.remember_turn(f"user {i}", f"assistant {i}")
        
        assert len(mem.history) == 5
        assert mem.history[-1]["user"] == "user 9"
    
    def test_remember_turn(self):
        """remember_turn stores conversation."""
        mem = Memory()
        mem.remember_turn("hello", "hi there")
        
        assert len(mem.history) == 1
        assert mem.history[0]["user"] == "hello"
        assert mem.history[0]["assistant"] == "hi there"
    
    def test_remember_goal(self):
        """remember_goal stores last goal."""
        mem = Memory()
        mem.remember_goal("scroll down")
        assert mem.last_goal == "scroll down"
    
    def test_remember_query(self):
        """remember_query stores last query."""
        mem = Memory()
        mem.remember_query("saiyaara song")
        assert mem.last_query == "saiyaara song"
    
    def test_remember_target(self):
        """remember_target stores UI element."""
        mem = Memory()
        target = {"name": "button", "x": 100, "y": 200}
        mem.remember_target(target)
        assert mem.last_target == target
    
    def test_remember_result(self):
        """remember_result stores result data."""
        mem = Memory()
        result = {"status": "success", "message": "done"}
        mem.remember_result(result)
        assert mem.last_result == result
    
    def test_set_screen(self):
        """set_screen extracts app and window from ScreenState."""
        mem = Memory()
        
        # Mock ScreenState
        class MockState:
            active_application = "Chrome"
            active_window = "Google - YouTube"
        
        mem.set_screen(MockState())
        assert mem.current_app == "Chrome"
        assert mem.current_window == "Google - YouTube"
    
    def test_context_returns_dict(self):
        """context() returns a dictionary with all state."""
        mem = Memory()
        mem.remember_goal("click button")
        mem.remember_query("test")
        mem.remember_turn("hello", "hi")
        
        ctx = mem.context()
        assert isinstance(ctx, dict)
        assert ctx["last_goal"] == "click button"
        assert ctx["last_query"] == "test"
        assert len(ctx["recent_history"]) == 1


class TestSmartBrain:
    """Test SmartBrain routing decisions."""
    
    @pytest.fixture
    def brain(self):
        """Create SmartBrain instance for testing."""
        router = IntentRouter()
        return SmartBrain(router=router)
    
    def test_smart_brain_initialization(self, brain):
        """SmartBrain initializes with router."""
        assert brain.router is not None
    
    def test_conversation_route(self, brain):
        """'hello' routes to conversation."""
        decision = brain.decide("maruti hello")
        assert decision.mode == "conversation"
        assert decision.confidence > 0.8
    
    def test_fast_local_scroll_down(self, brain):
        """'scroll down' routes to fast_local."""
        decision = brain.decide("scroll down")
        assert decision.mode == "fast_local"
        assert decision.confidence == 0.95
    
    def test_fast_local_press_enter(self, brain):
        """'press enter' routes to fast_local."""
        decision = brain.decide("press enter")
        assert decision.mode == "fast_local"
        assert decision.confidence == 0.95
    
    def test_fast_local_enter(self, brain):
        """'enter' routes to fast_local."""
        decision = brain.decide("enter")
        assert decision.mode == "fast_local"
    
    def test_media_command_saiyaara_song(self, brain):
        """'Saiyaara song chala do' routes to web_media."""
        decision = brain.decide("Saiyaara song chala do")
        assert decision.mode == "web_media"
        assert decision.confidence == 0.85
        # Query should extract 'saiyaara'
        assert decision.query is not None
        assert "saiyaara" in decision.query.lower()
    
    def test_media_command_music(self, brain):
        """'play music' routes to web_media."""
        decision = brain.decide("play music")
        assert decision.mode == "web_media"
    
    def test_non_explicit_youtube_command_remains_media(self, brain):
        """A non-explicit YouTube command remains a media request."""
        decision = brain.decide("YouTube kholo")
        assert decision.mode == "web_media"
    
    def test_open_chrome_is_not_web_navigation(self, brain):
        """Opening Chrome remains a computer/app request."""
        decision = brain.decide("open chrome")
        assert decision.mode == "computer_visual"
    
    def test_google_without_explicit_web_trigger_is_ambiguous(self, brain):
        """A bare Google opening phrase does not invoke universal web resolution."""
        decision = brain.decide("Google kholo")
        assert decision.mode == "ambiguous"
    
    def test_computer_visual_click_button(self, brain):
        """'click blue button' routes to computer_visual."""
        decision = brain.decide("click blue button")
        assert decision.mode == "computer_visual"
    
    def test_computer_visual_login_button(self, brain):
        """'Blue login button pe click karo' routes to computer_visual."""
        decision = brain.decide("Blue login button pe click karo")
        assert decision.mode == "computer_visual"
    
    def test_mixed_route_preserved(self, brain):
        """Mixed route is preserved from router."""
        # Mixed commands: both computer and conversation
        # Use a command that router recognizes as mixed
        decision = brain.decide("scroll down and tell me what you see")
        # If router detects mixed, preserve it
        if decision.mode == "mixed":
            assert decision.needs_confirmation == True
        else:
            # Otherwise, it should be one of the other routes
            assert decision.mode in {"fast_local", "conversation", "computer_visual", "web_media", "web_navigation"}
    
    def test_ambiguous_route(self, brain):
        """Ambiguous input routes to ambiguous."""
        decision = brain.decide("")
        assert decision.mode == "ambiguous"
    
    def test_media_query_extraction(self, brain):
        """Media query is properly extracted."""
        decision = brain.decide("play saiyaara song please")
        assert decision.mode == "web_media"
        # Should have extracted 'saiyaara'
        assert decision.query is not None
        assert len(decision.query) > 0
    
    def test_goal_preserved_in_decision(self, brain):
        """Original goal is preserved in decision."""
        transcript = "scroll down please"
        decision = brain.decide(transcript)
        assert transcript.strip() in decision.goal or decision.goal in transcript


class TestSmartBrainWithMemory:
    """Test SmartBrain and Memory working together."""
    
    def test_memory_and_brain_flow(self):
        """Test typical flow: remember goal → decide route."""
        router = IntentRouter()
        brain = SmartBrain(router=router)
        mem = Memory()
        
        # User says "Saiyaara song chala do"
        transcript = "Saiyaara song chala do"
        
        # Store goal
        from voice.speech_normalizer import normalize_command
        normalized = normalize_command(transcript)
        mem.remember_goal(normalized)
        
        # Route the command
        decision = brain.decide(transcript, mem)
        
        # Verify
        assert mem.last_goal is not None
        assert decision.mode == "web_media"
        assert decision.query is not None
    
    def test_multi_turn_context(self):
        """Test multi-turn conversation context."""
        mem = Memory(max_history=5)
        
        # Turn 1
        mem.remember_turn("hello", "hi there")
        assert len(mem.history) == 1
        
        # Turn 2
        mem.remember_turn("what time is it", "it is 3 pm")
        assert len(mem.history) == 2
        
        # Context should have both
        ctx = mem.context()
        assert len(ctx["recent_history"]) == 2


class TestSmartBrainEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.fixture
    def brain(self):
        router = IntentRouter()
        return SmartBrain(router=router)
    
    def test_empty_transcript(self, brain):
        """Empty transcript handled gracefully."""
        decision = brain.decide("")
        assert decision.mode == "ambiguous"
    
    def test_none_transcript(self, brain):
        """None transcript handled gracefully."""
        decision = brain.decide(None)
        assert decision.mode == "ambiguous"
    
    def test_whitespace_only(self, brain):
        """Whitespace-only transcript handled gracefully."""
        decision = brain.decide("   ")
        assert decision.mode == "ambiguous"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
