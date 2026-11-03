"""
Session Manager for handling multiple SSH sessions (MobaXterm-like tabs).
Each session has its own Backend instance for independent connections.
Connection history is shared across all sessions.
"""

from typing import Optional, List, Dict, Any
from PySide6.QtCore import QObject, Signal, Slot, QTimer, Property
from .backend import Backend
from .settings import (
    get_connection_history,
    add_connection_to_history,
    remove_connection_from_history,
)


class SessionManager(QObject):
    """Manages multiple SSH session backends for tabbed interface."""

    # Signals for QML
    sessionAdded = Signal(int)  # session index
    sessionRemoved = Signal(int)  # session index
    sessionUpdated = Signal(int)  # session index
    activeSessionChanged = Signal(int)  # session index
    errorOccurred = Signal(str)
    statusChanged = Signal(str)
    connectionHistoryChanged = Signal(list)  # shared connection history

    def __init__(self) -> None:
        super().__init__()
        self._sessions: List[Dict[str, Any]] = []
        self._active_session_index: int = -1
        self._next_session_id: int = 1
        self._connection_history: List[dict] = []
        self._load_connection_history()

    @property
    def active_session_index(self) -> int:
        return self._active_session_index

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    @Slot(result=int)
    def getSessionCount(self) -> int:
        """Number of active sessions (exposed to QML as a callable)."""
        return len(self._sessions)

    @Slot(result=int)
    def addSession(self) -> int:
        """Create a new session with its own Backend instance."""
        session_id = self._next_session_id
        self._next_session_id += 1

        backend = Backend()
        session = {
            "id": session_id,
            "backend": backend,
            "name": f"Session {session_id}",
            "connected": False,
            "host": "",
            "port": 22,
            "username": "",
        }

        self._sessions.append(session)
        index = len(self._sessions) - 1

        # If this is the first session, make it active
        if self._active_session_index == -1:
            self._active_session_index = index
            self.activeSessionChanged.emit(index)

        self.sessionAdded.emit(index)
        return index

    @Slot(int)
    def removeSession(self, index: int) -> None:
        """Remove a session and clean up its backend."""
        if 0 <= index < len(self._sessions):
            session = self._sessions[index]
            backend = session["backend"]

            # Disconnect if connected
            if session["connected"]:
                backend.disconnect()

            # Let worker threads finish so they cannot emit signals into
            # the backend we are about to delete ("Signal source has been deleted").
            for worker in list(backend._workers):
                worker.join(timeout=2.0)

            # Clean up backend
            backend.deleteLater()

            self._sessions.pop(index)
            self.sessionRemoved.emit(index)

            # Adjust active session index
            if self._active_session_index >= len(self._sessions):
                self._active_session_index = len(self._sessions) - 1
                if self._active_session_index >= 0:
                    self.activeSessionChanged.emit(self._active_session_index)

    @Slot(int)
    def setActiveSession(self, index: int) -> None:
        """Switch to a different session."""
        if 0 <= index < len(self._sessions) and index != self._active_session_index:
            self._active_session_index = index
            self.activeSessionChanged.emit(index)

    @Slot(int, result="QVariant")
    def getSessionBackend(self, index: int):
        """Get the Backend instance for a session."""
        if 0 <= index < len(self._sessions):
            return self._sessions[index]["backend"]
        return None

    @Slot(int, result=dict)
    def getSessionInfo(self, index: int) -> dict:
        """Get session metadata."""
        if 0 <= index < len(self._sessions):
            session = self._sessions[index]
            return {
                "id": session["id"],
                "name": session["name"],
                "connected": session["connected"],
                "host": session["host"],
                "port": session["port"],
                "username": session["username"],
            }
        return {}

    @Slot(int, str, str, int, str)
    def updateSessionInfo(self, index: int, name: str, host: str, port: int, username: str) -> None:
        """Update session metadata after connection."""
        if 0 <= index < len(self._sessions):
            self._sessions[index]["name"] = name
            self._sessions[index]["host"] = host
            self._sessions[index]["port"] = port
            self._sessions[index]["username"] = username
            self.sessionUpdated.emit(index)

    @Slot(int, bool)
    def setSessionConnected(self, index: int, connected: bool) -> None:
        """Update session connection status."""
        if 0 <= index < len(self._sessions):
            self._sessions[index]["connected"] = connected
            self.sessionUpdated.emit(index)

    @Slot(result=int)
    def getActiveSessionIndex(self) -> int:
        return self._active_session_index

    @Slot(result="QVariantList")
    def getAllSessions(self):
        """Get list of all sessions for QML."""
        result = []
        for i, session in enumerate(self._sessions):
            result.append({
                "index": i,
                "id": session["id"],
                "name": session["name"],
                "connected": session["connected"],
                "host": session["host"],
                "port": session["port"],
                "username": session["username"],
            })
        return result

    # -- Shared connection history -------------------------------------------

    @Property("QVariantList", notify=connectionHistoryChanged)
    def connectionHistory(self) -> List[dict]:
        """Shared connection history across all sessions."""
        return self._connection_history

    @Slot(result="QVariantList")
    def getConnectionHistory(self) -> List[dict]:
        """Get shared connection history (exposed to QML)."""
        return self._connection_history

    @Slot()
    def reloadConnectionHistory(self) -> None:
        """Reload connection history from settings and notify QML."""
        self._load_connection_history()

    def _load_connection_history(self) -> None:
        """Load connection history from shared settings file."""
        history = get_connection_history()
        for item in history:
            host = item.get("host", "")
            port = item.get("port", 22)
            username = item.get("username", "")
            remote_path = item.get("remote_path", "")
            item["displayText"] = f"{host}:{port} ({username}@{remote_path})"
        self._connection_history = history
        self.connectionHistoryChanged.emit(history)

    @Slot(str, str, int, str, str, bool, str)
    def saveConnection(
        self,
        host: str,
        username: str,
        port: int,
        remote_path: str,
        key_filename: str,
        save_password: bool,
        password: str,
    ) -> None:
        """Save a connection profile to the shared history."""
        add_connection_to_history(
            host=host,
            username=username,
            port=port,
            remote_path=remote_path,
            key_filename=key_filename or None,
            save_password=save_password,
            password=password if save_password else None,
        )
        self.reloadConnectionHistory()

    @Slot(str, str, int, str)
    def removeConnection(
        self, host: str, username: str, port: int, remote_path: str
    ) -> None:
        """Remove a connection from the shared history."""
        if remove_connection_from_history(host, username, port, remote_path):
            self.reloadConnectionHistory()
            self.connectionRemoved.emit(f"{host}:{port}")

    connectionRemoved = Signal(str)

    def cleanup(self) -> None:
        """Clean up all sessions on shutdown."""
        for session in self._sessions:
            backend = session["backend"]
            if session["connected"]:
                backend.disconnect()
            # Let worker threads finish so they cannot emit signals into
            # backends we are about to delete ("Signal source has been deleted").
            for worker in list(backend._workers):
                worker.join(timeout=2.0)
            backend.deleteLater()
        self._sessions.clear()
        self._active_session_index = -1