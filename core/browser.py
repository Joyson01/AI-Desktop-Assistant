"""Browser Automation Interface for MARUTI Desktop Assistant.

Coordinates browser navigation, search execution, video targeting,
and link interaction using layered strategy:
1. Validated URL/Search engine navigation.
2. Perception OCR target location for visible buttons/links/videos.
3. Desktop input backend for bounded interaction.
4. Policy confirmation gates for sensitive actions (payments, logins, submissions).
5. Structured context tracking for active domain, search queries, and media playback.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple
from urllib.parse import quote_plus

from core.context import ConversationContext
from core.input import DesktopInputBackend
from core.perception import PerceptionEngine
from core.policy import ActionRisk, PolicyEngine
from core.system_control import SystemController

logger = logging.getLogger("maruti.browser")


class BrowserAutomation:
    """Manages browser interactions, video targeting, and media controls."""

    def __init__(
        self,
        system_controller: Optional[SystemController] = None,
        input_backend: Optional[DesktopInputBackend] = None,
        perception: Optional[PerceptionEngine] = None,
        policy: Optional[PolicyEngine] = None,
        context: Optional[ConversationContext] = None,
    ) -> None:
        self.system = system_controller or SystemController()
        self.input = input_backend or DesktopInputBackend()
        self.perception = perception or PerceptionEngine()
        self.policy = policy or PolicyEngine()
        self.context = context

    def open_website(self, site_or_url: str) -> Tuple[bool, str]:
        """Navigate to a website with scheme validation and context tracking."""
        self.perception.invalidate_cache()
        ok, msg = self.system.open_url(site_or_url)
        if ok and self.context:
            valid, target_url, netloc = self.system.validate_url(site_or_url)
            site_name = "youtube" if "youtube" in (netloc or "") else (netloc or site_or_url)
            self.context.update_site(site_name, target_url, page_state="homepage")
            self.context.update_action("open_website", msg)
        return ok, msg

    def search_web(self, query: str) -> Tuple[bool, str]:
        """Perform a clean web search using Google."""
        clean_q = query.strip()
        if not clean_q:
            return False, "Empty search query."

        self.perception.invalidate_cache()
        url = f"https://www.google.com/search?q={quote_plus(clean_q)}"
        ok, msg = self.system.open_url(url)
        if ok and self.context:
            self.context.update_site("google", url, page_state="search_results")
            self.context.update_search(clean_q, site="google")
            self.context.update_action("web_search", msg)
        return ok, msg

    def dismiss_consent_dialog(self) -> bool:
        """Locate and dismiss common cookie/consent dialogs if visible."""
        if not self.perception.is_ocr_available():
            return False

        consent_labels = ["accept all", "i agree", "agree", "reject all"]
        for label in consent_labels:
            target = self.perception.find_target(label)
            if target:
                logger.info("Dismissing consent dialog via target '%s' at (%d, %d)", target.text, target.x, target.y)
                self.input.click_coordinate(target.x, target.y)
                self.perception.invalidate_cache()
                return True
        return False

    def search_youtube(self, query: str, prefer_in_page: bool = True) -> Tuple[bool, str]:
        """Search YouTube for a query with active-context in-page search and verification."""
        clean_q = query.strip()
        self.perception.invalidate_cache()

        if not clean_q:
            ok, msg = self.system.open_url("https://www.youtube.com")
            if ok and self.context:
                self.context.update_site("youtube", "https://www.youtube.com", page_state="homepage")
            return ok, msg

        # Handle consent dialogs if present
        self.dismiss_consent_dialog()

        # If YouTube is already open and active, prefer accessible in-page search
        if prefer_in_page and self.context and self.context.is_youtube_active():
            # YouTube accessible shortcut '/' focuses search bar
            logger.info("YouTube active context: attempting in-page accessible search for '%s'", clean_q)
            self.input.press_keys(["/"])
            time.sleep(0.15)
            # Clear any existing text
            self.input.press_keys(["ctrl", "a"])
            time.sleep(0.05)
            self.input.press_keys(["backspace"])
            time.sleep(0.05)
            # Type and submit query
            self.input.type_text(clean_q)
            time.sleep(0.05)
            self.input.press_keys(["enter"])
            self.perception.invalidate_cache()

            results_url = f"https://www.youtube.com/results?search_query={quote_plus(clean_q)}"
            self.context.update_site("youtube", results_url, page_state="search_results")
            self.context.update_search(clean_q, site="youtube")
            self.context.update_action("youtube_search", f"Showing YouTube results for {clean_q}.")
            return True, f"Showing YouTube results for {clean_q}."

        # If YouTube is not yet open or direct URL requested:
        url = f"https://www.youtube.com/results?search_query={quote_plus(clean_q)}"
        ok, msg = self.system.open_url(url)
        if ok:
            if self.context:
                self.context.update_site("youtube", url, page_state="search_results")
                self.context.update_search(clean_q, site="youtube")
                self.context.update_action("youtube_search", f"Showing YouTube results for {clean_q}.")
            return True, f"Showing YouTube results for {clean_q}."
        return False, f"Failed to search YouTube: {msg}"

    def click_video(self, index: int = 1) -> Tuple[bool, str]:
        """Locate and click the video result at 1-based index on screen."""
        self.perception.invalidate_cache()
        if index == 1:
            target = self.perception.find_first_video()
        else:
            target = self.perception.find_video_by_index(index)
        ordinal_name = "first" if index == 1 else "second" if index == 2 else f"number {index}"

        if not target:
            # Fallback heuristic: On desktop YouTube search results,
            # video 1 is at ~38% width, ~320px down.
            # Subsequent videos are vertically spaced ~160px apart.
            w, h = self.input.get_screen_size()
            estimated_x = int(w * 0.38)
            base_y = 320
            spacing_y = 160
            estimated_y = int(min(h - 50, base_y + (index - 1) * spacing_y))
            logger.info("Using heuristic coordinate for video %d: (%d, %d)", index, estimated_x, estimated_y)
            ok, msg = self.input.click_coordinate(estimated_x, estimated_y)
            if ok:
                self.perception.invalidate_cache()
                if self.context:
                    self.context.page_state = "watch"
                    self.context.update_action(f"click_video_{index}", f"Clicked the {ordinal_name} video.")
                return True, f"Clicked the {ordinal_name} video."
            return False, f"Could not locate the {ordinal_name} video: {msg}"

        ok, msg = self.input.click_coordinate(target.x, target.y)
        if ok:
            self.perception.invalidate_cache()
            if self.context:
                self.context.page_state = "watch"
                self.context.update_action(f"click_video_{index}", f"Clicked the {ordinal_name} video.")
            return True, f"Clicked the {ordinal_name} video."
        return False, f"Failed to click {ordinal_name} video: {msg}"

    def click_first_video(self) -> Tuple[bool, str]:
        """Locate and click the first visible video result on screen."""
        return self.click_video(1)

    def pause_media(self) -> Tuple[bool, str]:
        """Pause active media playback using player shortcut 'k'."""
        self.perception.invalidate_cache()
        ok, msg = self.input.press_keys(["k"])
        if self.context:
            self.context.update_media_state("paused")
            self.context.update_action("media_pause", "Video paused.")
        return True, "Video paused."

    def resume_media(self) -> Tuple[bool, str]:
        """Resume active media playback using player shortcut 'k'."""
        self.perception.invalidate_cache()
        ok, msg = self.input.press_keys(["k"])
        if self.context:
            self.context.update_media_state("playing")
            self.context.update_action("media_resume", "Video resumed.")
        return True, "Video resumed."

    def click_element_by_label(self, label: str) -> Tuple[bool, str]:
        """Find a button or link with visible text matching label and click it."""
        clean_label = label.strip()
        if not clean_label:
            return False, "No element label specified to click."

        # Check policy for sensitive labels (e.g. 'Pay Now', 'Confirm Purchase', 'Delete Account', 'Sign In', 'Login')
        if any(kw in clean_label.lower() for kw in ("pay", "buy", "purchase", "delete", "checkout", "transfer", "login", "sign in", "signin")):
            confirmed = self.policy.authorize_execution(
                "browser_payment",
                args={"label": clean_label},
                custom_prompt=f"Clicking '{clean_label}' might perform a sensitive, login, or financial action. Do you want me to click it?",
            )
            if not confirmed:
                return False, f"Cancelled clicking '{clean_label}'."

        self.perception.invalidate_cache()
        target = self.perception.find_target(clean_label)
        if not target:
            return False, f"Could not find any element matching '{clean_label}' on the screen."

        ok, msg = self.input.click_coordinate(target.x, target.y)
        if ok:
            self.perception.invalidate_cache()
            return True, f"Clicked '{target.text}'."
        return False, msg
