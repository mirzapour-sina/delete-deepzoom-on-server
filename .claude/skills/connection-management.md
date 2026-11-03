---
name: connection-management
description: Skill for managing SSH connections, connection history, and session handling in the Remote DeepZoom Folder Cleaner app
---

# Connection Management

This skill covers managing SSH connections, connection profiles, and multi-session handling in the Remote DeepZoom Folder Cleaner app.

## When to use

Use this skill when you need to:
- Add or modify SSH connection logic
- Manage connection history and saved profiles
- Handle host key verification
- Work with multiple sessions (tabbed interface)
- Modify connection UI forms or dialogs

## Session management (SessionManager)

Located in `deepzoom_cleaner/session_manager.py`. Each session has its own `Backend` instance for independent connections.

Key methods:
- `addSession()` - Create a new session with its own Backend
- `removeSession(index)` - Remove a session and clean up its backend
- `setActiveSession(index)` - Switch active session
- `getSessionBackend(index)` - Get the Backend for a session
- `getSessionInfo(index)` - Get session metadata
- `updateSessionInfo(index, name, host, port, username)` - Update session info after connection
- `setSessionConnected(index, connected)` - Update connection status
- `getAllSessions()` - Get list of all sessions for QML
- `cleanup()` - Clean up all sessions on shutdown

## Connection flow

1. User fills connection form (host, username, port, remote_path, key_file, password)
2. `connectAndLoad()` is called on the Backend
3. Backend opens SSH client via `_open_client(settings)`
4. If host key is unknown, `hostKeyTrustRequested` signal is emitted
5. User accepts/rejects host key via `acceptPendingHostKey()` / `rejectPendingHostKey()`
6. Backend lists folders and entries, emits `foldersLoaded` and `entriesLoaded`
7. Connection is saved to history via `add_connection_to_history()`
8. `connectionStatusChanged("connected", message)` is emitted

## Connection history

Stored in `~/.deepzoom-cleaner/settings.json` under `connection_history`. Max 10 connections kept. Each profile includes:
- host, username, port, remote_path
- key_filename, password (only if save_password preference is enabled)
- last_used timestamp

## Host key verification

Known hosts stored at `~/.deepzoom-cleaner/known_hosts`. Uses paramiko's HostKeys for storage. Unknown host keys trigger `HostKeyConfirmationRequired` exception.

## Files to reference

- `deepzoom_cleaner/session_manager.py` - Session management
- `deepzoom_cleaner/backend.py` - Connection logic (connectAndLoad, _open_client, host key handling)
- `deepzoom_cleaner/settings.py` - Connection history persistence
- `qml/SessionTab.qml` - Connection form UI
- `qml/Main.qml` - Session tab bar and management dialogs