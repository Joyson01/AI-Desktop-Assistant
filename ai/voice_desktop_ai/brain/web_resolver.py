from __future__ import annotations

import base64
import webbrowser
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qs, quote_plus, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import re
import json


@dataclass
class SearchResult:
    """Represents a web search result."""
    title: str
    url: str
    confidence: float


@dataclass
class OfficialSiteResult(SearchResult):
    domain: str = ""
    resolver: str = ""
    reason: str = ""


class WebResolver:
    """
    Resolves web queries into safe, searchable URLs.
    Caches results to avoid regenerating the same queries.
    Does NOT scrape, select first results, autoplay, or use unofficial APIs.
    """
    
    # Confidence for generated search URLs (below exact-result matching)
    SEARCH_RESULT_CONFIDENCE = 0.75
    
    def __init__(self, grok=None, gemini=None):
        """Initialize WebResolver with empty cache."""
        self.cache: dict[str, SearchResult] = {}
        self.grok = grok
        self.gemini = gemini
        self._ai_rejected_response = False
    
    def resolve_youtube(self, query: str) -> SearchResult | None:
        """
        Generate a safe YouTube search URL for the given query.
        
        Args:
            query: Search query (e.g., "Saiyaara")
            
        Returns:
            SearchResult with YouTube search URL, or None if query is empty
        """
        # Handle empty/None queries
        if not query or not isinstance(query, str):
            return None
        
        # Normalize query
        normalized = self._normalize_query(query)
        if not normalized:
            return None
        
        # Check cache first
        if normalized in self.cache:
            return self.cache[normalized]
        
        # Generate YouTube search URL
        encoded_query = quote_plus(normalized)
        youtube_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        
        # Create and cache result
        result = SearchResult(
            title=f"YouTube search: {normalized}",
            url=youtube_url,
            confidence=self.SEARCH_RESULT_CONFIDENCE,
        )
        
        self.cache[normalized] = result
        return result

    def resolve_website(self, target: str) -> SearchResult | None:
        """Resolve a target through configured providers, then local fallbacks."""
        normalized = self._normalize_query(target)
        if not normalized or normalized in {"this", "that", "it", "wahi", "yeh", "woh"}:
            return None
        provider_result = self.resolve_website_with_ai(normalized)
        if provider_result:
            return provider_result
        fallback_target = self._normalize_website_target(normalized)
        known_sites = {
            "gmail": "https://mail.google.com/",
            "google maps": "https://maps.google.com/",
            "google docs": "https://docs.google.com/",
            "google do": "https://docs.google.com/",
            "chrome": "https://www.google.com/chrome/",
            "physics wallah": "https://www.pw.live/",
            "physics wala": "https://www.pw.live/",
            "pw": "https://www.pw.live/",
            "unacademy": "https://unacademy.com/",
            "uidai": "https://uidai.gov.in/",
            "udiai": "https://uidai.gov.in/",
            "whatsapp": "https://web.whatsapp.com/",
            "chatgpt": "https://chatgpt.com/",
            "youtube": "https://www.youtube.com/",
        }
        known_url = known_sites.get(fallback_target)
        if known_url:
            print(f"[WEB] target={normalized} fallback=official_site result=resolved url={known_url}")
            return OfficialSiteResult(normalized, known_url, 0.99, urlsplit(known_url).hostname or "", "local", "Known official site")
        if "." in fallback_target and " " not in fallback_target:
            candidate = fallback_target if fallback_target.startswith(("http://", "https://")) else f"https://{fallback_target}"
            if self._safe_url(candidate):
                return OfficialSiteResult(normalized, candidate, 0.95, urlsplit(candidate).hostname or "", "local", "Explicit domain")

        if self._ai_rejected_response:
            print(f"[WEB] target={normalized} fallback=official_site result=skipped reason=provider_response_rejected")
            return None

        local = self._deterministic_official_result(fallback_target)
        if local:
            print(f"[WEB] target={normalized} fallback=official_site result=resolved url={local.url}")
            return local
        print(f"[WEB] target={normalized} fallback=official_site result=unresolved")
        return None

    def resolve_website_with_ai(self, target: str) -> OfficialSiteResult | None:
        """Ask Gemini first, then Grok, for one validated official-site URL."""
        self._ai_rejected_response = False
        candidates = []
        for name, provider in (("gemini", self.gemini), ("grok", self.grok)):
            if provider is None or not getattr(provider, "configured", True):
                print(f"[WEB] target={target} provider={name} result=unavailable")
                continue
            self._ai_rejected_response = True
            candidate = self._ask_provider(name, provider, target)
            print(f"[WEB] target={target} provider={name} result={'resolved' if candidate else 'unresolved'}")
            if candidate:
                candidates.append(candidate)
                if name == "gemini" and self.grok is None:
                    return candidate
            elif name == "gemini":
                continue
        if not candidates:
            return None
        best = candidates[0]
        if len(candidates) > 1 and any(item.domain != best.domain for item in candidates[1:]):
            return None
        return best

    def _deterministic_official_result(self, target):
        ranked = sorted(self._search_official_candidates(target), key=lambda item: item[2], reverse=True)
        if not ranked or ranked[0][2] < 0.8 or (len(ranked) > 1 and ranked[0][2] - ranked[1][2] < 0.12):
            return None
        title, url, confidence = ranked[0]
        return OfficialSiteResult(title, url, confidence, urlsplit(url).hostname or "", "local", "High-confidence official result")

    def _ask_provider(self, name, provider, target):
        if provider is None or not getattr(provider, "configured", True):
            return None
        print(f"[WEB] target={target} provider={name} request=start")
        prompt = (
            f"Find the official website URL for: {target}\n"
            "Return ONLY the official website URL.\n"
            "Do not return YouTube, YouTube search results, Google search results, "
            "Bing search results, Wikipedia, social media, review websites, "
            "third-party directories, articles, or app-store pages.\n"
            "If the target is a product, service, or company, return its official website."
        )
        try:
            if name == "grok":
                response = provider.resolve_website(prompt)
                print(f"[WEB] target={target} provider={name} raw_response={response!r}")
                if isinstance(response, str) and "not configured yet" in response.lower():
                    self._ai_rejected_response = False
                return self._candidate_from_response(response, target, name)
            if callable(getattr(provider, "answer", None)):
                response = provider.answer(prompt)
                print(f"[WEB] target={target} provider={name} raw_response={response!r}")
                if isinstance(response, str) and "not configured yet" in response.lower():
                    self._ai_rejected_response = False
                return self._candidate_from_response(response, target, name)
            # Preserve compatibility with existing structured provider doubles.
            response = provider.analyze(prompt)
            print(f"[WEB] target={target} provider={name} raw_response={response!r}")
            payload = json.loads(response) if isinstance(response, str) else response
            return self._candidate_from_payload(payload, target, name)
        except Exception as error:
            print(f"[WEB] target={target} provider={name} request=failed error={type(error).__name__}")
            return None

    def _candidate_from_response(self, response, target, resolver):
        if isinstance(response, dict):
            return self._candidate_from_payload(response, target, resolver)
        if not isinstance(response, str):
            return None
        try:
            payload = json.loads(response)
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            candidate = self._candidate_from_payload(payload, target, resolver)
            if candidate:
                return candidate
        matches = re.findall(r"https?://[^\s<>\"']+", response)
        for value in matches:
            candidate = value.rstrip(".,);]}")
            normalized_url = self._normalize_official_url(candidate)
            if not normalized_url:
                print(f"[WEB] target={target} provider={resolver} validation=rejected reason=invalid_url")
                continue
            if not self._is_allowed_official_host(normalized_url, target):
                print(f"[WEB] target={target} provider={resolver} validation=rejected reason=blocked_destination")
                continue
            hostname = urlsplit(normalized_url).hostname or ""
            print(f"[WEB] target={target} provider={resolver} extracted_url={normalized_url} validation=valid")
            return OfficialSiteResult(
                str(target),
                normalized_url,
                0.9,
                hostname.removeprefix("www."),
                resolver,
                "Official URL extracted from provider response",
            )
        return None

    def _candidate_from_payload(self, payload, target, resolver):
        if not isinstance(payload, dict):
            return None
        url = payload.get("official_url")
        confidence = payload.get("confidence", 0.0)
        if not isinstance(url, str) or not isinstance(confidence, (int, float)):
            return None
        normalized_url = self._normalize_official_url(url)
        if not normalized_url or not self._is_allowed_official_host(normalized_url, target) or confidence < 0.8:
            return None
        hostname = urlsplit(normalized_url).hostname or ""
        declared_domain = str(payload.get("official_domain") or payload.get("domain") or "").lower().removeprefix("www.")
        if declared_domain and not self._same_domain(hostname, declared_domain):
            return None
        return OfficialSiteResult(
            str(payload.get("name") or target),
            normalized_url,
            min(float(confidence), 1.0),
            declared_domain or hostname.removeprefix("www."),
            resolver,
            str(payload.get("reason") or "Official website candidate"),
        )

    @staticmethod
    def _normalize_official_url(url):
        value = str(url).strip()
        if not value.startswith(("http://", "https://")):
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.scheme == "http":
            parsed = parsed._replace(scheme="https")
        return urlunsplit(parsed)

    @staticmethod
    def _same_domain(hostname, declared):
        host = hostname.lower().removeprefix("www.")
        domain = declared.lower().removeprefix("www.")
        return host == domain or host.endswith("." + domain)

    @staticmethod
    def _is_allowed_official_host(url, target=""):
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower().removeprefix("www.")
        normalized_target = WebResolver._normalize_query(target)
        is_wikipedia_target = "wikipedia" in normalized_target
        if not hostname or (hostname.endswith(".wikipedia.org") and not is_wikipedia_target):
            return False
        if hostname in {"bing.com", "duckduckgo.com"}:
            return False
        if hostname == "google.com" and parsed.path.rstrip("/").lower() in {"/search", "/url"}:
            return False
        if hostname == "youtube.com":
            return normalized_target == "youtube" and parsed.path.rstrip("/") in {"", "/"}
        return True

    def _search_official_candidates(self, target):
        query = quote_plus(f"{target} official website")
        html = ""
        for endpoint in (
            f"https://html.duckduckgo.com/html/?q={query}",
            f"https://www.bing.com/search?q={query}",
        ):
            try:
                request = Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})
                html = urlopen(request, timeout=5).read().decode("utf-8", errors="ignore")
            except Exception:
                continue
            if "anomaly.js" not in html and ("result__a" in html or "b_algo" in html):
                break
        if not html:
            return []
        tokens = set(re.findall(r"[a-z0-9]+", target.lower()))
        results = []
        patterns = (
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        )
        matches = []
        for pattern in patterns:
            matches.extend(re.finditer(pattern, html, re.I | re.S))
        for match in matches:
            url = self._unwrap_search_url(unescape(match.group(1)))
            title = re.sub(r"<[^>]+>", "", unescape(match.group(2))).strip()
            if not self._safe_url(url) or not self._is_allowed_official_host(url, target):
                continue
            parsed_url = urlsplit(url)
            host = parsed_url.hostname or ""
            title_lower = title.lower()
            if any(marker in title_lower for marker in (
                "download", "review", "directory", "news", "article", "careers",
                "affiliate", "login", "sign in", "partner", "seller",
            )):
                continue
            host_tokens = set(re.findall(r"[a-z0-9]+", host))
            score = 0.45 + 0.1 * len(tokens & host_tokens) + (0.2 if "official" in title.lower() else 0)
            target_slug = "".join(tokens)
            host_slug = host.lower().removeprefix("www.").split(".", 1)[0]
            if target_slug and host_slug == target_slug:
                score += 0.25
            if parsed_url.path.rstrip("/") == "":
                score += 0.1
            else:
                score -= 0.1
            if re.search(r"/(?:login|account|careers?|affiliate|seller|partner)(?:/|$)", parsed_url.path, re.I):
                score -= 0.2
            results.append((title, url, min(score, 0.95)))
        return results

    @staticmethod
    def _unwrap_search_url(url):
        parsed = urlsplit(url)
        if parsed.hostname != "www.bing.com" or parsed.path != "/ck/a":
            return url
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if not encoded.startswith("a1"):
            return url
        try:
            padded = encoded[2:] + "=" * (-len(encoded[2:]) % 4)
            return base64.urlsafe_b64decode(padded).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return url

    @staticmethod
    def _safe_url(url):
        parsed = urlsplit(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password
    
    @staticmethod
    def open_url(url: str) -> bool:
        """
        Open a URL in the default web browser.
        
        Args:
            url: URL to open
            
        Returns:
            True if browser opened successfully, False otherwise
        """
        if not url or not isinstance(url, str):
            return False
        
        try:
            return webbrowser.open(url)
        except Exception:
            return False
    
    def clear_cache(self):
        """Clear the results cache."""
        self.cache.clear()
    
    @staticmethod
    def _normalize_query(query: str) -> str:
        """
        Normalize a query string for caching and URL generation.
        
        Args:
            query: Raw query string
            
        Returns:
            Normalized query (lowercase, stripped whitespace)
        """
        if not query:
            return ""
        
        # Convert to string and lowercase
        normalized = str(query).lower().strip()
        
        # Remove excessive whitespace
        normalized = " ".join(normalized.split())
        
        return normalized

    @staticmethod
    def _normalize_website_target(target: str) -> str:
        """Normalize common speech-recognition variants before provider/fallback lookup."""
        return {
            "chat gpt": "chatgpt",
            "chat gpd": "chatgpt",
            "chat jpt": "chatgpt",
            "chat gptt": "chatgpt",
            "gpt": "chatgpt",
        }.get(target, target)
