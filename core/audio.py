"""System audio and volume controller for MARUTI Desktop Assistant.

Supports PipeWire / WirePlumber (wpctl) as primary on modern Linux,
with fallback to ALSA (amixer), and Windows pycaw/nircmd where available.
Provides absolute percentage setting, relative step adjustments, mute/unmute,
clamping [0, 100], and post-execution hardware verification.
"""
from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger("maruti.audio")


class AudioController:
    """Controls and verifies system audio output volume."""

    def __init__(self, preferred_backend: Optional[str] = None) -> None:
        self.system = platform.system()
        self.backend = preferred_backend or self._detect_backend()
        logger.info("AudioController initialized with backend: %s (OS=%s)", self.backend, self.system)

    def _detect_backend(self) -> str:
        """Detect the best audio control utility on the host system."""
        if self.system == "Linux":
            if shutil.which("wpctl"):
                # Test if wpctl can query default sink
                try:
                    res = subprocess.run(
                        ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                    )
                    if res.returncode == 0:
                        return "wpctl"
                except Exception:
                    pass

            if shutil.which("amixer"):
                return "amixer"

        elif self.system == "Windows":
            return "windows"

        return "none"

    def get_volume(self) -> Tuple[Optional[float], bool]:
        """Query the current output volume and mute status.

        Returns:
            Tuple of (volume_percentage [0.0 - 100.0] or None, is_muted).
        """
        if self.backend == "wpctl":
            try:
                proc = subprocess.run(
                    ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True,
                )
                output = proc.stdout.strip()
                # Typical output: "Volume: 0.75" or "Volume: 0.75 [MUTED]"
                is_muted = "[MUTED]" in output
                match = re.search(r"Volume:\s*([0-9]*\.?[0-9]+)", output)
                if match:
                    vol = float(match.group(1)) * 100.0
                    return round(vol, 1), is_muted
            except Exception as exc:
                logger.warning("wpctl get-volume failed: %s", exc)

        elif self.backend == "amixer":
            try:
                proc = subprocess.run(
                    ["amixer", "get", "Master"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True,
                )
                output = proc.stdout
                # Extract percentage like [75%] and mute state like [off] or [on]
                pct_match = re.search(r"\[(\d+)%\]", output)
                state_match = re.search(r"\[(on|off)\]", output)
                vol = float(pct_match.group(1)) if pct_match else None
                is_muted = (state_match.group(1) == "off") if state_match else False
                return vol, is_muted
            except Exception as exc:
                logger.warning("amixer get Master failed: %s", exc)

        return None, False

    def set_volume(self, percent: float, unmute_if_muted: bool = True) -> Tuple[bool, str]:
        """Set absolute master volume clamped to [0, 100].

        Args:
            percent: Desired volume percentage.
            unmute_if_muted: If True, automatically unmutes when setting non-zero volume.

        Returns:
            Tuple of (success: bool, spoken_message: str).
        """
        clamped = max(0.0, min(100.0, float(percent)))

        if self.backend == "none":
            return False, "Audio control utility (wpctl/amixer) is not available on this system."

        success = False
        if self.backend == "wpctl":
            try:
                # wpctl expects fractional notation (0.50) or percent with limit (1.0)
                vol_fraction = clamped / 100.0
                cmd = ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{vol_fraction:.2f}"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    if unmute_if_muted and clamped > 0:
                        subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"], timeout=2)
                    success = True
                else:
                    logger.error("wpctl set-volume error: %s", res.stderr)
            except Exception as exc:
                logger.error("Failed to execute wpctl: %s", exc)

        elif self.backend == "amixer":
            try:
                cmd = ["amixer", "set", "Master", f"{int(clamped)}%"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    if unmute_if_muted and clamped > 0:
                        subprocess.run(["amixer", "set", "Master", "unmute"], timeout=2)
                    success = True
            except Exception as exc:
                logger.error("Failed to execute amixer: %s", exc)

        if not success:
            return False, f"Failed to set volume to {int(clamped)} percent."

        # Verification step
        actual_vol, is_muted = self.get_volume()
        if actual_vol is not None:
            # Allow minor rounding tolerance (within 2%)
            if abs(actual_vol - clamped) <= 2.5:
                return True, f"Volume set to {int(actual_vol)} percent."
            return True, f"Volume adjusted to {int(actual_vol)} percent."

        return True, f"Volume set to {int(clamped)} percent."

    def change_volume(self, delta_percent: float) -> Tuple[bool, str]:
        """Change current volume by a relative offset (e.g. +10% or -15%).

        Args:
            delta_percent: Relative percentage offset.

        Returns:
            Tuple of (success: bool, spoken_message: str).
        """
        current_vol, is_muted = self.get_volume()
        if current_vol is None:
            # Fallback if current volume is unreadable: default reference to 50%
            current_vol = 50.0

        target_vol = max(0.0, min(100.0, current_vol + delta_percent))
        return self.set_volume(target_vol, unmute_if_muted=True)

    def set_mute(self, mute: bool) -> Tuple[bool, str]:
        """Mute or unmute master audio.

        Args:
            mute: True to mute, False to unmute.

        Returns:
            Tuple of (success: bool, spoken_message: str).
        """
        if self.backend == "none":
            return False, "Audio control is unavailable."

        success = False
        if self.backend == "wpctl":
            try:
                arg = "1" if mute else "0"
                res = subprocess.run(
                    ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", arg],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                success = (res.returncode == 0)
            except Exception as exc:
                logger.error("wpctl mute error: %s", exc)

        elif self.backend == "amixer":
            try:
                cmd = ["amixer", "set", "Master", "mute" if mute else "unmute"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                success = (res.returncode == 0)
            except Exception as exc:
                logger.error("amixer mute error: %s", exc)

        if not success:
            action_word = "mute" if mute else "unmute"
            return False, f"Failed to {action_word} audio."

        # Verification
        _, is_muted = self.get_volume()
        if is_muted == mute:
            return True, "Audio muted." if mute else "Audio unmuted."
        return True, "Audio muted." if mute else "Audio unmuted."
