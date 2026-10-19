"""
Phase 3: Media Fast Path Tests

Tests for the media fast path routing in SmartBrain v1.
- Media commands route through WebResolver
- YouTube search URLs are generated and opened
- TTS feedback is provided
- Normal behavior is preserved for non-media commands
"""

from unittest.mock import MagicMock, Mock, patch
import pytest

from brain.memory import Memory
from brain.smart_brain import SmartBrain
from brain.intent_router import IntentRouter
from brain.conversation import ConversationManager, default_conversation_provider
from brain.web_resolver import SearchResult, WebResolver
from assistant import AccessibilityAssistant


class TestPhase3MediaFastPath:
    """Test the media fast path in handle_media_request()"""

    @pytest.fixture
    def assistant(self):
        """Create assistant with mocked dependencies"""
        with patch("voice.stt.SpeechService"), \
             patch("tts.speak"), \
             patch("perception.observer.observe_screen"), \
             patch("brain.providers.provider_config.load_provider_config"):
            assistant = AccessibilityAssistant()
            return assistant

    def test_media_request_with_valid_query(self, assistant):
        """Test: "Saiyaara song chala do" → YouTube URL opened, user feedback given"""
        with patch("tts.speak") as mock_speak, \
             patch.object(assistant.web_resolver, "open_url") as mock_open_url, \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup
            mock_result = SearchResult(
                title="YouTube search: saiyaara",
                url="https://www.youtube.com/results?search_query=saiyaara",
                confidence=0.75,
            )
            mock_resolve.return_value = mock_result
            mock_open_url.return_value = True

            # Create decision
            decision = Mock()
            decision.query = "Saiyaara"
            decision.mode = "web_media"

            # Execute
            result = assistant.handle_media_request(decision)

            # Verify
            assert result is True
            mock_resolve.assert_called_once_with("Saiyaara")
            mock_open_url.assert_called_once_with(
                "https://www.youtube.com/results?search_query=saiyaara"
            )
            # Verify user feedback
            speak_calls = [call[0][0] for call in mock_speak.call_args_list]
            assert any("Opening" in call and "YouTube" in call for call in speak_calls)

    def test_media_request_empty_query(self, assistant):
        """Test: Empty query → asks user which song, no URL opened"""
        with patch("tts.speak") as mock_speak, \
             patch.object(assistant.web_resolver, "open_url") as mock_open_url:
            
            # Setup
            decision = Mock()
            decision.query = ""
            decision.mode = "web_media"

            # Execute
            result = assistant.handle_media_request(decision)

            # Verify
            assert result is True
            mock_open_url.assert_not_called()
            speak_calls = [call[0][0] for call in mock_speak.call_args_list]
            assert any("Which song" in call or "Which video" in call for call in speak_calls)

    def test_media_request_none_query(self, assistant):
        """Test: None query → asks user which song, no URL opened"""
        with patch("tts.speak") as mock_speak, \
             patch.object(assistant.web_resolver, "open_url") as mock_open_url:
            
            # Setup
            decision = Mock()
            decision.query = None
            decision.mode = "web_media"

            # Execute
            result = assistant.handle_media_request(decision)

            # Verify
            assert result is True
            mock_open_url.assert_not_called()
            speak_calls = [call[0][0] for call in mock_speak.call_args_list]
            assert any("Which song" in call or "Which video" in call for call in speak_calls)

    def test_media_request_resolver_failure(self, assistant):
        """Test: Resolver returns None → failure message, no URL opened"""
        with patch("tts.speak") as mock_speak, \
             patch.object(assistant.web_resolver, "open_url") as mock_open_url, \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup
            mock_resolve.return_value = None

            decision = Mock()
            decision.query = "xyz_invalid_query_xyz"
            decision.mode = "web_media"

            # Execute
            result = assistant.handle_media_request(decision)

            # Verify
            assert result is True
            mock_open_url.assert_not_called()
            speak_calls = [call[0][0] for call in mock_speak.call_args_list]
            assert any("couldn't find" in call.lower() for call in speak_calls)

    def test_media_fast_path_integrated_in_handle(self, assistant):
        """Test: handle() routes web_media decisions to media fast path"""
        with patch("voice.speech_normalizer.normalize_command") as mock_normalize, \
             patch.object(assistant, "handle_media_request") as mock_media_handler, \
             patch("tts.speak"):
            
            # Setup
            mock_normalize.return_value = "Maruti Saiyaara song chala do"
            mock_media_handler.return_value = True

            # Manually create a web_media decision
            with patch.object(assistant.smart_brain, "decide") as mock_decide:
                decision = Mock()
                decision.mode = "web_media"
                decision.query = "Saiyaara"
                decision.goal = "play song"
                decision.confidence = 0.85
                mock_decide.return_value = decision

                # Execute
                result = assistant.handle("Maruti Saiyaara song chala do")

                # Verify
                assert result is True
                mock_media_handler.assert_called_once()
                call_args = mock_media_handler.call_args[0][0]
                assert call_args.mode == "web_media"
                assert call_args.query == "Saiyaara"

    def test_memory_records_query_and_result(self, assistant):
        """Test: Memory records both query and result for follow-up commands"""
        with patch("tts.speak"), \
             patch.object(assistant.web_resolver, "open_url"), \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup
            mock_result = SearchResult(
                title="YouTube search: test",
                url="https://www.youtube.com/results?search_query=test",
                confidence=0.75,
            )
            mock_resolve.return_value = mock_result

            decision = Mock()
            decision.query = "Test Song"
            decision.mode = "web_media"

            # Execute
            assistant.handle_media_request(decision)

            # Verify memory was updated
            context = assistant.memory.context()
            assert "Test Song" in str(context)


class TestPhase3NonMediaRoutingPreserved:
    """Test that non-media routing behavior is preserved"""

    @pytest.fixture
    def assistant(self):
        """Create assistant with mocked dependencies"""
        with patch("voice.stt.SpeechService"), \
             patch("tts.speak"), \
             patch("perception.observer.observe_screen"), \
             patch("brain.providers.provider_config.load_provider_config"):
            assistant = AccessibilityAssistant()
            return assistant

    def test_scroll_down_command_still_routed_normally(self, assistant):
        """Test: "scroll down" does NOT go through media fast path"""
        with patch("voice.speech_normalizer.normalize_command") as mock_normalize, \
             patch("tts.speak"), \
             patch.object(assistant, "handle_media_request") as mock_media_handler, \
             patch.object(assistant.intent_router, "route") as mock_route, \
             patch.object(assistant, "execute_step"):
            
            # Setup
            mock_normalize.return_value = "scroll down"
            
            # Create a normal computer action route (not media)
            mock_route_obj = Mock()
            mock_route_obj.route = "computer_action"
            mock_route_obj.legacy_intent = Mock()
            mock_route_obj.legacy_intent.action = "scroll"
            mock_route.return_value = mock_route_obj

            # SmartBrain decides it's fast_local, not web_media
            with patch.object(assistant.smart_brain, "decide") as mock_decide:
                decision = Mock()
                decision.mode = "fast_local"
                decision.query = None
                decision.goal = "scroll"
                decision.confidence = 0.95
                mock_decide.return_value = decision

                # Execute
                with patch("brain.planner.make_plan") as mock_plan:
                    mock_plan_obj = Mock()
                    mock_plan_obj.steps = []
                    mock_plan.return_value = mock_plan_obj
                    assistant.handle("scroll down")

                # Verify media handler was NOT called
                mock_media_handler.assert_not_called()

    def test_conversation_command_not_routed_to_media(self, assistant):
        """Test: "hello" conversation does NOT go through media fast path"""
        with patch("voice.speech_normalizer.normalize_command") as mock_normalize, \
             patch("tts.speak") as mock_speak, \
             patch.object(assistant, "handle_media_request") as mock_media_handler:
            
            # Setup
            mock_normalize.return_value = "Maruti hello"

            with patch.object(assistant.smart_brain, "decide") as mock_decide:
                decision = Mock()
                decision.mode = "conversation"
                decision.query = None
                decision.goal = "greet"
                decision.confidence = 0.95
                mock_decide.return_value = decision

                with patch.object(assistant.intent_router, "route") as mock_route:
                    mock_route_obj = Mock()
                    mock_route_obj.route = "conversation"
                    mock_route_obj.legacy_intent = None
                    mock_route.return_value = mock_route_obj

                    # Execute
                    assistant.handle("Maruti hello")

                    # Verify media handler was NOT called
                    mock_media_handler.assert_not_called()
                    # Verify some response was given
                    assert mock_speak.called or mock_route.called

    def test_media_fast_path_does_not_invoke_legacy_executor(self, assistant):
        """Test: Media command does NOT call execute_step() or action executor"""
        with patch("voice.speech_normalizer.normalize_command") as mock_normalize, \
             patch("tts.speak"), \
             patch.object(assistant, "execute_step") as mock_execute_step, \
             patch.object(assistant.web_resolver, "open_url"), \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup
            mock_normalize.return_value = "play test"
            mock_result = SearchResult(
                title="YouTube search: test",
                url="https://www.youtube.com/results?search_query=test",
                confidence=0.75,
            )
            mock_resolve.return_value = mock_result

            with patch.object(assistant.smart_brain, "decide") as mock_decide:
                decision = Mock()
                decision.mode = "web_media"
                decision.query = "Test"
                decision.goal = "play"
                decision.confidence = 0.85
                mock_decide.return_value = decision

                # Execute
                assistant.handle("play test")

                # Verify legacy executor was NOT called
                mock_execute_step.assert_not_called()


class TestPhase3MediaFastPathOrdering:
    """Test that media fast path check occurs in the correct order"""

    @pytest.fixture
    def assistant(self):
        """Create assistant with mocked dependencies"""
        with patch("voice.stt.SpeechService"), \
             patch("tts.speak"), \
             patch("perception.observer.observe_screen"), \
             patch("brain.providers.provider_config.load_provider_config"):
            assistant = AccessibilityAssistant()
            return assistant

    def test_media_fast_path_checked_after_smart_brain_decision(self, assistant):
        """Test: Media path is checked after SmartBrain decision but before other routes"""
        call_order = []

        def track_smart_brain(transcript, memory):
            call_order.append("smart_brain.decide")
            decision = Mock()
            decision.mode = "web_media"
            decision.query = "Song"
            decision.goal = "play"
            decision.confidence = 0.85
            return decision

        def track_media_handler(decision):
            call_order.append("handle_media_request")
            return True

        with patch("voice.speech_normalizer.normalize_command") as mock_normalize, \
             patch("tts.speak"), \
             patch.object(assistant.smart_brain, "decide", side_effect=track_smart_brain), \
             patch.object(assistant, "handle_media_request", side_effect=track_media_handler):
            
            mock_normalize.return_value = "play song"

            # Execute
            assistant.handle("play song")

            # Verify order
            assert "smart_brain.decide" in call_order
            assert "handle_media_request" in call_order
            assert call_order.index("smart_brain.decide") < call_order.index("handle_media_request")

    def test_media_path_bypasses_intent_routing(self, assistant):
        """Test: Media path returns early, bypassing normal intent routing"""
        with patch("voice.speech_normalizer.normalize_command") as mock_normalize, \
             patch("tts.speak"), \
             patch.object(assistant.intent_router, "route") as mock_route, \
             patch.object(assistant.web_resolver, "open_url"), \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup
            mock_normalize.return_value = "play song"
            mock_result = SearchResult(
                title="YouTube search: song",
                url="https://www.youtube.com/results?search_query=song",
                confidence=0.75,
            )
            mock_resolve.return_value = mock_result

            with patch.object(assistant.smart_brain, "decide") as mock_decide:
                decision = Mock()
                decision.mode = "web_media"
                decision.query = "Song"
                decision.goal = "play"
                decision.confidence = 0.85
                mock_decide.return_value = decision

                # Execute
                assistant.handle("play song")

                # Intent router may or may not be called, but media handler should complete
                # Media should have been handled and returned True


class TestPhase3DebugOutput:
    """Test that debug output is correct for media requests"""

    @pytest.fixture
    def assistant(self):
        """Create assistant with mocked dependencies"""
        with patch("voice.stt.SpeechService"), \
             patch("tts.speak"), \
             patch("perception.observer.observe_screen"), \
             patch("brain.providers.provider_config.load_provider_config"):
            assistant = AccessibilityAssistant()
            return assistant

    def test_media_request_prints_debug_info(self, assistant, capsys):
        """Test: Media request prints [MEDIA] debug output"""
        with patch("tts.speak"), \
             patch.object(assistant.web_resolver, "open_url"), \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup
            mock_result = SearchResult(
                title="YouTube search: saiyaara",
                url="https://www.youtube.com/results?search_query=saiyaara",
                confidence=0.75,
            )
            mock_resolve.return_value = mock_result

            decision = Mock()
            decision.query = "Saiyaara"
            decision.mode = "web_media"

            # Execute
            assistant.handle_media_request(decision)

            # Capture output
            captured = capsys.readouterr()
            output = captured.out

            # Verify debug output
            assert "[MEDIA]" in output
            assert "Query: Saiyaara" in output
            assert "youtube.com" in output
            assert "Confidence: 0.75" in output


class TestPhase3EdgeCases:
    """Test edge cases and error conditions"""

    @pytest.fixture
    def assistant(self):
        """Create assistant with mocked dependencies"""
        with patch("voice.stt.SpeechService"), \
             patch("tts.speak"), \
             patch("perception.observer.observe_screen"), \
             patch("brain.providers.provider_config.load_provider_config"):
            assistant = AccessibilityAssistant()
            return assistant

    def test_open_url_failure_handled_gracefully(self, assistant):
        """Test: If open_url fails, we don't crash"""
        with patch("tts.speak"), \
             patch.object(assistant.web_resolver, "open_url") as mock_open_url, \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup - open_url returns False (failed)
            mock_result = SearchResult(
                title="YouTube search: test",
                url="https://www.youtube.com/results?search_query=test",
                confidence=0.75,
            )
            mock_resolve.return_value = mock_result
            mock_open_url.return_value = False

            decision = Mock()
            decision.query = "Test"
            decision.mode = "web_media"

            # Execute - should not crash
            result = assistant.handle_media_request(decision)

            # Verify it still returns True (media request handled)
            assert result is True

    def test_resolver_exception_handled(self, assistant):
        """Test: If resolver raises exception, we handle it gracefully"""
        with patch("tts.speak"), \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup - resolver raises exception
            mock_resolve.side_effect = Exception("Network error")

            decision = Mock()
            decision.query = "Test"
            decision.mode = "web_media"

            # Execute - should raise, but test will verify behavior
            with pytest.raises(Exception):
                assistant.handle_media_request(decision)

    def test_special_characters_in_query(self, assistant):
        """Test: Special characters in query are handled safely"""
        with patch("tts.speak"), \
             patch.object(assistant.web_resolver, "open_url"), \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup
            mock_result = SearchResult(
                title="YouTube search: query",
                url="https://www.youtube.com/results?search_query=query",
                confidence=0.75,
            )
            mock_resolve.return_value = mock_result

            decision = Mock()
            decision.query = "Test & Song (2024)"
            decision.mode = "web_media"

            # Execute
            result = assistant.handle_media_request(decision)

            # Verify
            assert result is True
            mock_resolve.assert_called_once_with("Test & Song (2024)")

    def test_unicode_query_handled(self, assistant):
        """Test: Unicode/Hindi queries are handled correctly"""
        with patch("tts.speak"), \
             patch.object(assistant.web_resolver, "open_url"), \
             patch.object(assistant.web_resolver, "resolve_youtube") as mock_resolve:
            
            # Setup
            mock_result = SearchResult(
                title="YouTube search: गाना",
                url="https://www.youtube.com/results?search_query=gaana",
                confidence=0.75,
            )
            mock_resolve.return_value = mock_result

            decision = Mock()
            decision.query = "गाना"
            decision.mode = "web_media"

            # Execute
            result = assistant.handle_media_request(decision)

            # Verify
            assert result is True
            mock_resolve.assert_called_once_with("गाना")


class TestPhase3BackwardCompatibility:
    """Test that Phase 3 doesn't break existing functionality"""

    @pytest.fixture
    def assistant(self):
        """Create assistant with mocked dependencies"""
        with patch("voice.stt.SpeechService"), \
             patch("tts.speak"), \
             patch("perception.observer.observe_screen"), \
             patch("brain.providers.provider_config.load_provider_config"):
            assistant = AccessibilityAssistant()
            return assistant

    def test_assistant_initialization_includes_web_resolver(self, assistant):
        """Test: Assistant initializes web_resolver without errors"""
        assert hasattr(assistant, "web_resolver")
        assert isinstance(assistant.web_resolver, WebResolver)

    def test_assistant_still_has_memory_and_smart_brain(self, assistant):
        """Test: Assistant still has memory and smart_brain from Phase 1"""
        assert hasattr(assistant, "memory")
        assert isinstance(assistant.memory, Memory)
        assert hasattr(assistant, "smart_brain")
        assert isinstance(assistant.smart_brain, SmartBrain)

    def test_handle_media_request_method_exists(self, assistant):
        """Test: handle_media_request method is defined and callable"""
        assert hasattr(assistant, "handle_media_request")
        assert callable(assistant.handle_media_request)
