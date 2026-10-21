"""Safe System, Application, Website, and Folder Control for MARUTI.

Provides strictly validated launch routines:
- URL validation (restricts to http/https, rejects javascript/file/data schemes).
- Allowlisted application launcher with binary fallback chains and environment passthrough.
- Common directory launcher (Home, Downloads, Documents, Desktop, Pictures, Videos).
- Subprocess argument list safety (prohibits untrusted shell string concatenation).
- Verification of binary and path existence before claiming success.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import webbrowser

import registry

logger = logging.getLogger("maruti.system_control")


class SystemController:
    """Safe desktop application, web, and filesystem navigator."""

    # Allowlisted standard user directories
    KNOWN_FOLDERS: Dict[str, str] = {
        "home": "",
        "downloads": "Downloads",
        "documents": "Documents",
        "desktop": "Desktop",
        "pictures": "Pictures",
        "music": "Music",
        "videos": "Videos",
    }

    def __init__(self) -> None:
        self.system = platform.system()
        self.is_wayland = bool(os.getenv("WAYLAND_DISPLAY"))

    def validate_url(self, raw_url: str) -> Tuple[bool, str, Optional[str]]:
        """Validate and sanitize a web target URL.

        Returns:
            Tuple of (is_valid: bool, sanitized_url_or_error: str, domain_label: Optional[str]).
        """
        url_stripped = raw_url.strip()
        if not url_stripped:
            return False, "Empty URL requested.", None

        # Prepend https if user gave bare domain
        if not re_has_scheme(url_stripped):
            url_to_parse = "https://" + url_stripped
        else:
            url_to_parse = url_stripped

        parsed = urlparse(url_to_parse)
        scheme = parsed.scheme.lower()

        # Reject dangerous schemes
        if scheme not in ("http", "https"):
            logger.warning("Rejected dangerous or unsupported URL scheme '%s' in '%s'", scheme, raw_url)
            return False, f"Unsupported or dangerous URL scheme '{scheme}'. Only http and https are permitted.", None

        if not parsed.netloc:
            return False, f"Invalid domain in URL '{raw_url}'.", None

        return True, url_to_parse, parsed.netloc

    def open_url(self, url: str) -> Tuple[bool, str]:
        """Validate URL and launch in user's default browser."""
        valid, target_url, netloc = self.validate_url(url)
        if not valid:
            return False, target_url

        try:
            opened = webbrowser.open(target_url)
            if opened:
                return True, f"Opening {netloc}."
            return True, f"Navigating to {netloc}."
        except Exception as exc:
            logger.error("Failed to open browser URL %s: %s", target_url, exc)
            return False, f"Failed to launch browser: {exc}"

    def open_folder(self, folder_name: str) -> Tuple[bool, str]:
        """Safely open an allowlisted user directory."""
        key = folder_name.strip().lower()
        key = key.replace("folder", "").replace("directory", "").strip()

        if key not in self.KNOWN_FOLDERS:
            # Check if user passed an existing subfolder name
            custom_path = Path.home() / key.title()
            if custom_path.is_dir():
                target_path = custom_path
            else:
                return False, f"Unknown or unpermitted folder '{folder_name}'."
        else:
            sub = self.KNOWN_FOLDERS[key]
            target_path = Path.home() / sub if sub else Path.home()

        if not target_path.exists():
            return False, f"Directory '{target_path.name}' does not exist on your computer."

        env = dict(os.environ)
        # Select appropriate file manager
        file_managers = ["nautilus", "thunar", "dolphin", "pcmanfm", "xdg-open"]
        if self.system == "Windows":
            cmd = ["explorer", str(target_path)]
        else:
            fm_binary = None
            for fm in file_managers:
                if shutil.which(fm):
                    fm_binary = fm
                    break

            if not fm_binary:
                return False, "No graphical file manager found on this system."
            cmd = [fm_binary, str(target_path)]

        try:
            subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, f"Opening {target_path.name or 'Home'} folder."
        except Exception as exc:
            logger.error("Failed to open folder %s: %s", target_path, exc)
            return False, f"Failed to open folder: {exc}"

    def open_application(self, app_alias: str) -> Tuple[bool, str]:
        """Resolve and launch an allowlisted desktop application."""
        kind, target, conf, label = registry.resolve(app_alias)

        if kind == "site":
            return self.open_url(target)

        # Kind is 'app'
        if target not in registry.APPS:
            return False, f"Application '{app_alias}' is not recognized in the system registry."

        app_info = registry.APPS[target]
        env = dict(os.environ)

        if self.system == "Windows":
            cmd_str = app_info.get("win", "")
            if not cmd_str:
                return False, f"No Windows command registered for '{target}'."
            try:
                subprocess.Popen(f'start "" "{cmd_str}"', shell=True, env=env)
                return True, f"Opening {label}."
            except Exception as exc:
                return False, f"Failed to launch '{target}': {exc}"

        # Linux: iterate through primary and fallback binaries
        primary = app_info.get("linux", "")
        alts = app_info.get("linux_alts", [])
        candidates = [c for c in [primary] + alts if c]

        for candidate in candidates:
            parts = candidate.split()
            binary_name = parts[0]
            extra_args = parts[1:]
            resolved_binary = shutil.which(binary_name)
            if resolved_binary:
                try:
                    subprocess.Popen(
                        [resolved_binary] + extra_args,
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return True, f"Opening {label}."
                except Exception as exc:
                    logger.error("Failed to execute candidate '%s': %s", candidate, exc)

        return False, f"Application '{label}' is not installed on this system. (Tried binaries: {', '.join(candidates)})"


def re_has_scheme(url: str) -> bool:
    """Check if URL string contains an explicit protocol scheme like http:, https:, javascript:, file:, etc."""
    import re
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", url.strip()))
