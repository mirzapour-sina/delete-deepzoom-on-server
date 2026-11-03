"""
Settings management for connection history and user preferences.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional


SETTINGS_DIR = Path.home() / ".deepzoom-cleaner"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


DEFAULT_SETTINGS = {
    "connection_history": [],
    "last_connection": None,
    "window_geometry": {"width": 1120, "height": 800},
    "ui_preferences": {
        "theme": "light",
        "show_hidden_files": False,
        "confirm_destructive": True,
    }
}


def load_settings() -> dict[str, Any]:
    """Load settings from file, returning defaults if file doesn't exist."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge with defaults to handle new settings
            merged = DEFAULT_SETTINGS.copy()
            merged.update(data)
            if "ui_preferences" in data:
                merged["ui_preferences"] = {**DEFAULT_SETTINGS["ui_preferences"], **data["ui_preferences"]}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict[str, Any]) -> bool:
    """Save settings to file."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def add_connection_to_history(
    host: str,
    username: str,
    port: int,
    remote_path: str,
    key_filename: Optional[str] = None,
    save_password: bool = False,
    password: Optional[str] = None,
    connection_name: Optional[str] = None,
) -> dict[str, Any]:
    """Add or update a connection in history."""
    settings = load_settings()
    history = settings.get("connection_history", [])

    # Create connection profile
    profile = {
        "host": host,
        "username": username,
        "port": port,
        "remote_path": remote_path,
        "key_filename": key_filename,
        "password": password if save_password else None,
        "connection_name": connection_name or "",
        "last_used": None,  # Will be set on use
    }

    # Remove existing entry with same host+username+port+path
    history = [h for h in history if not (
        h.get("host") == host and
        h.get("username") == username and
        h.get("port") == port and
        h.get("remote_path") == remote_path
    )]

    # Add to front of history
    history.insert(0, profile)

    # Keep only last 10 connections
    settings["connection_history"] = history[:10]
    settings["last_connection"] = profile
    save_settings(settings)
    return profile


def get_connection_history() -> list[dict[str, Any]]:
    """Get the connection history list."""
    settings = load_settings()
    return settings.get("connection_history", [])


def get_last_connection() -> Optional[dict[str, Any]]:
    """Get the last used connection profile."""
    settings = load_settings()
    return settings.get("last_connection")


def update_last_used(host: str, username: str, port: int, remote_path: str) -> None:
    """Update the last_used timestamp for a connection."""
    settings = load_settings()
    history = settings.get("connection_history", [])
    for h in history:
        if (h.get("host") == host and
            h.get("username") == username and
            h.get("port") == port and
            h.get("remote_path") == remote_path):
            from datetime import datetime
            h["last_used"] = datetime.now().isoformat()
            break
    if settings.get("last_connection"):
        lc = settings["last_connection"]
        if (lc.get("host") == host and
            lc.get("username") == username and
            lc.get("port") == port and
            lc.get("remote_path") == remote_path):
            from datetime import datetime
            lc["last_used"] = datetime.now().isoformat()
    save_settings(settings)


def remove_connection_from_history(host: str, username: str, port: int, remote_path: str) -> bool:
    """Remove a connection from history."""
    settings = load_settings()
    history = settings.get("connection_history", [])
    original_len = len(history)
    history = [h for h in history if not (
        h.get("host") == host and
        h.get("username") == username and
        h.get("port") == port and
        h.get("remote_path") == remote_path
    )]
    settings["connection_history"] = history
    if settings.get("last_connection"):
        lc = settings["last_connection"]
        if (lc.get("host") == host and
            lc.get("username") == username and
            lc.get("port") == port and
            lc.get("remote_path") == remote_path):
            settings["last_connection"] = history[0] if history else None
    save_settings(settings)
    return len(history) < original_len


def get_ui_preference(key: str, default: Any = None) -> Any:
    """Get a UI preference value."""
    settings = load_settings()
    return settings.get("ui_preferences", {}).get(key, default)


def set_ui_preference(key: str, value: Any) -> None:
    """Set a UI preference value."""
    settings = load_settings()
    if "ui_preferences" not in settings:
        settings["ui_preferences"] = {}
    settings["ui_preferences"][key] = value
    save_settings(settings)


def get_window_geometry() -> dict[str, int]:
    """Get saved window geometry."""
    settings = load_settings()
    return settings.get("window_geometry", DEFAULT_SETTINGS["window_geometry"])


def save_window_geometry(width: int, height: int) -> None:
    """Save window geometry."""
    settings = load_settings()
    settings["window_geometry"] = {"width": width, "height": height}
    save_settings(settings)