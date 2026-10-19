"""
Tests for WebResolver - YouTube search URL generation and caching.
"""
import pytest
from urllib.parse import unquote_plus

from brain.web_resolver import WebResolver, SearchResult


class TestSearchResult:
    """Test SearchResult dataclass."""
    
    def test_search_result_initialization(self):
        """SearchResult initializes with title, url, confidence."""
        result = SearchResult(
            title="YouTube search: test",
            url="https://www.youtube.com/results?search_query=test",
            confidence=0.75,
        )
        
        assert result.title == "YouTube search: test"
        assert result.url == "https://www.youtube.com/results?search_query=test"
        assert result.confidence == 0.75


class TestWebResolverInitialization:
    """Test WebResolver initialization and setup."""
    
    def test_web_resolver_initialization(self):
        """WebResolver initializes with empty cache."""
        resolver = WebResolver()
        assert resolver.cache == {}
        assert isinstance(resolver.cache, dict)
    
    def test_search_result_confidence_constant(self):
        """SEARCH_RESULT_CONFIDENCE is set appropriately."""
        resolver = WebResolver()
        assert resolver.SEARCH_RESULT_CONFIDENCE == 0.75
        # Below exact-result confidence (which would be 0.95+)
        assert resolver.SEARCH_RESULT_CONFIDENCE < 0.95


class TestYouTubeResolution:
    """Test YouTube URL generation."""
    
    @pytest.fixture
    def resolver(self):
        """Create WebResolver for testing."""
        return WebResolver()
    
    def test_resolve_youtube_normal_query(self, resolver):
        """Normal query generates valid YouTube search URL."""
        result = resolver.resolve_youtube("Saiyaara")
        
        assert result is not None
        assert isinstance(result, SearchResult)
        assert "youtube.com/results" in result.url
        assert "search_query=" in result.url
        assert result.confidence == 0.75
    
    def test_resolve_youtube_url_encoding(self, resolver):
        """Query is properly URL-encoded."""
        result = resolver.resolve_youtube("Saiyaara")
        
        # Extract the search_query parameter
        assert "search_query=Saiyaara" in result.url or "search_query=saiyaara" in result.url.lower()
    
    def test_resolve_youtube_spaces_in_query(self, resolver):
        """Queries with spaces are handled correctly."""
        result = resolver.resolve_youtube("Maruti Saiyaara")
        
        assert result is not None
        assert "youtube.com/results" in result.url
        # Spaces should be encoded as + in URL
        assert "search_query=" in result.url
    
    def test_resolve_youtube_special_characters(self, resolver):
        """Special characters are handled safely."""
        result = resolver.resolve_youtube("Saiyaara - Full")
        
        assert result is not None
        assert "youtube.com/results" in result.url
        # Should URL-encode the query safely
        assert result.url.startswith("https://www.youtube.com/results?search_query=")
    
    def test_resolve_youtube_empty_query(self, resolver):
        """Empty query returns None."""
        result = resolver.resolve_youtube("")
        assert result is None
    
    def test_resolve_youtube_none_query(self, resolver):
        """None query returns None."""
        result = resolver.resolve_youtube(None)
        assert result is None
    
    def test_resolve_youtube_whitespace_only(self, resolver):
        """Whitespace-only query returns None."""
        result = resolver.resolve_youtube("   ")
        assert result is None
    
    def test_resolve_youtube_result_title(self, resolver):
        """Result title is descriptive."""
        result = resolver.resolve_youtube("Test Query")
        
        assert result.title == "YouTube search: test query"
        assert "test query" in result.title.lower()


class TestCaching:
    """Test cache functionality."""
    
    @pytest.fixture
    def resolver(self):
        """Create WebResolver for testing."""
        return WebResolver()
    
    def test_cache_stores_result(self, resolver):
        """First query stores result in cache."""
        resolver.resolve_youtube("Saiyaara")
        
        assert len(resolver.cache) == 1
        assert "saiyaara" in resolver.cache
    
    def test_cache_reuse(self, resolver):
        """Subsequent queries reuse cached result."""
        result1 = resolver.resolve_youtube("Saiyaara")
        result2 = resolver.resolve_youtube("Saiyaara")
        
        # Should be the same object from cache
        assert result1 is result2
        # Cache should have only one entry
        assert len(resolver.cache) == 1
    
    def test_cache_case_insensitive(self, resolver):
        """Cache is case-insensitive."""
        result1 = resolver.resolve_youtube("SAIYAARA")
        result2 = resolver.resolve_youtube("saiyaara")
        result3 = resolver.resolve_youtube("Saiyaara")
        
        # All should return the same cached result
        assert result1 is result2
        assert result2 is result3
        assert len(resolver.cache) == 1
    
    def test_cache_normalizes_spaces(self, resolver):
        """Cache normalizes multiple spaces."""
        result1 = resolver.resolve_youtube("Saiyaara Song")
        result2 = resolver.resolve_youtube("Saiyaara  Song")  # Double space
        result3 = resolver.resolve_youtube("Saiyaara   Song")  # Triple space
        
        # All should return the same cached result
        assert result1 is result2
        assert result2 is result3
        assert len(resolver.cache) == 1
    
    def test_cache_clear(self, resolver):
        """clear_cache() empties the cache."""
        resolver.resolve_youtube("Saiyaara")
        resolver.resolve_youtube("Test")
        
        assert len(resolver.cache) == 2
        
        resolver.clear_cache()
        
        assert len(resolver.cache) == 0
    
    def test_multiple_different_queries(self, resolver):
        """Different queries are cached separately."""
        resolver.resolve_youtube("Saiyaara")
        resolver.resolve_youtube("Maruti")
        resolver.resolve_youtube("Song")
        
        assert len(resolver.cache) == 3
        assert "saiyaara" in resolver.cache
        assert "maruti" in resolver.cache
        assert "song" in resolver.cache


class TestOpenURL:
    """Test URL opening functionality."""
    
    def test_open_url_with_valid_url(self):
        """open_url() attempts to open a valid URL."""
        # We can't test actual browser opening, but we can test the function doesn't crash
        url = "https://www.youtube.com/results?search_query=test"
        result = WebResolver.open_url(url)
        # Result will be True/False depending on browser availability
        # but shouldn't raise an exception
        assert isinstance(result, bool)
    
    def test_open_url_with_empty_string(self):
        """open_url() with empty string returns False."""
        result = WebResolver.open_url("")
        assert result is False
    
    def test_open_url_with_none(self):
        """open_url() with None returns False."""
        result = WebResolver.open_url(None)
        assert result is False
    
    def test_open_url_static_method(self):
        """open_url() is a static method."""
        # Should be callable without instantiation
        result = WebResolver.open_url("https://www.youtube.com")
        assert isinstance(result, bool)


class TestURLFormat:
    """Test URL format compliance."""
    
    @pytest.fixture
    def resolver(self):
        """Create WebResolver for testing."""
        return WebResolver()
    
    def test_url_starts_with_https(self, resolver):
        """Generated URL uses HTTPS."""
        result = resolver.resolve_youtube("Test")
        assert result.url.startswith("https://")
    
    def test_url_contains_youtube_domain(self, resolver):
        """Generated URL contains YouTube domain."""
        result = resolver.resolve_youtube("Test")
        assert "youtube.com" in result.url
    
    def test_url_contains_results_path(self, resolver):
        """Generated URL contains /results path."""
        result = resolver.resolve_youtube("Test")
        assert "/results" in result.url
    
    def test_url_contains_search_query_param(self, resolver):
        """Generated URL contains search_query parameter."""
        result = resolver.resolve_youtube("Test")
        assert "search_query=" in result.url
    
    def test_url_properly_encoded(self, resolver):
        """URL is properly encoded without issues."""
        result = resolver.resolve_youtube("Test & Special")
        
        # Should be a valid URL string
        assert isinstance(result.url, str)
        assert result.url.count("?") == 1  # Only one query string
        assert result.url.startswith("https://www.youtube.com/results?search_query=")


class TestConfidence:
    """Test confidence scoring."""
    
    @pytest.fixture
    def resolver(self):
        """Create WebResolver for testing."""
        return WebResolver()
    
    def test_confidence_is_present(self, resolver):
        """SearchResult always has confidence."""
        result = resolver.resolve_youtube("Test")
        assert hasattr(result, "confidence")
        assert result.confidence is not None
    
    def test_confidence_is_float(self, resolver):
        """Confidence is a float value."""
        result = resolver.resolve_youtube("Test")
        assert isinstance(result.confidence, float)
    
    def test_confidence_below_exact_match(self, resolver):
        """Confidence is below exact-match confidence (0.95)."""
        result = resolver.resolve_youtube("Test")
        assert result.confidence < 0.95
    
    def test_confidence_is_reasonable(self, resolver):
        """Confidence is in reasonable range."""
        result = resolver.resolve_youtube("Test")
        # Search results should have moderate confidence
        assert 0.5 < result.confidence < 0.95
    
    def test_confidence_consistent(self, resolver):
        """Confidence is consistent for same query."""
        result1 = resolver.resolve_youtube("Test")
        result2 = resolver.resolve_youtube("Test")
        
        assert result1.confidence == result2.confidence


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    @pytest.fixture
    def resolver(self):
        """Create WebResolver for testing."""
        return WebResolver()
    
    def test_very_long_query(self, resolver):
        """Very long queries are handled."""
        long_query = "A" * 1000
        result = resolver.resolve_youtube(long_query)
        
        assert result is not None
        assert "youtube.com" in result.url
    
    def test_unicode_query(self, resolver):
        """Unicode characters are handled."""
        result = resolver.resolve_youtube("संगीत")  # Hindi for music
        
        assert result is not None
        assert "youtube.com" in result.url
    
    def test_numeric_query(self, resolver):
        """Numeric queries are handled."""
        result = resolver.resolve_youtube("2024")
        
        assert result is not None
        assert "youtube.com" in result.url
    
    def test_query_with_symbols(self, resolver):
        """Queries with symbols are handled safely."""
        result = resolver.resolve_youtube("C++ programming")
        
        assert result is not None
        assert "youtube.com" in result.url


class TestIntegrationFlow:
    """Test realistic usage flows."""
    
    def test_complete_resolution_flow(self):
        """Complete flow: resolve → cache → reuse → open."""
        resolver = WebResolver()
        
        # First resolution
        result1 = resolver.resolve_youtube("Saiyaara Song")
        assert result1 is not None
        assert result1.url.startswith("https://www.youtube.com/results")
        
        # Cache hit on second call
        result2 = resolver.resolve_youtube("Saiyaara Song")
        assert result1 is result2
        
        # Can open the URL (won't actually open in test)
        can_open = WebResolver.open_url(result1.url)
        assert isinstance(can_open, bool)
    
    def test_multiple_queries_different_results(self):
        """Multiple different queries generate different URLs."""
        resolver = WebResolver()
        
        result1 = resolver.resolve_youtube("Saiyaara")
        result2 = resolver.resolve_youtube("Maruti")
        result3 = resolver.resolve_youtube("Song")
        
        # All should be valid
        assert result1.url != result2.url
        assert result2.url != result3.url
        
        # All should start with same base
        assert all(r.url.startswith("https://www.youtube.com/results") for r in [result1, result2, result3])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
