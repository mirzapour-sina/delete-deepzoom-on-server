---
name: backend-development
description: Skill for working with the paramiko SSH backend in deepzoom_cleaner/backend.py
---

# Backend Development

This skill covers working with the Python backend (`deepzoom_cleaner/backend.py`) that provides SSH-based remote file operations via Paramiko, exposed to QML through PySide6 signals and slots.

## When to use

Use this skill when you need to:
- Add new remote file operations (rename, delete, compress, extract, etc.)
- Modify SSH connection handling or host key management
- Change file transfer behavior (upload/download via SFTP)
- Add new backend signals or slots exposed to QML
- Modify the remote Python scripts executed on the server

## Backend class structure

### Backend (QObject) in deepzoom_cleaner/backend.py

Key properties:
- `busy` - True while a background operation is running
- `connection_status` - Current connection status string
- `connection_message` - Current connection status message

Key signals:
- `entriesLoaded(path, entries)` - File/folder listing loaded
- `foldersLoaded(folders)` - Folder list loaded (for session tabs)
- `foldersRemoved(paths)` - Folders removed
- `connectionStatusChanged(status, message)` - Connection state changed
- `hostKeyTrustRequested(hostname, port, fingerprint)` - Host key needs verification
- `errorOccurred(message)` - Error to display
- `statusChanged(message)` - Status bar message
- `uploadProgress(filename, current, total)` - Upload progress
- `downloadProgress(filename, current, total)` - Download progress
- `uploadCompleted(remote_path, success, message)` - Upload finished
- `downloadCompleted(local_path, success, message)` - Download finished
- `fileContentLoaded(path, info)` - File content loaded for editing
- `fileWritten(path, success, message)` - File write finished

Key slots (exposed to QML):
- `connectAndLoad(host, username, port_text, remote_path, key_filename, password)`
- `disconnect()`
- `navigate(path)`
- `refresh()`
- `removeFolders(paths)`
- `deleteSelection(paths)`
- `renameEntry(path, new_name)`
- `createDirectory(parent, name)`
- `compressSelection(paths, archive_name, format_name)`
- `extractArchive(archive_path, destination)`
- `readFileContent(path)`
- `writeFileContent(path, content_b64, is_binary)`
- `uploadFile(local_path, remote_path)`
- `downloadFile(remote_path, local_path)`
- `showHiddenFiles()` / `setShowHiddenFiles(value)`
- `loadDiskUsage()`, `loadBlockDevices()`
- `loadDirectoryStats(path)`, `loadEntryProperties(path)`

## Remote Python scripts

The backend executes Python scripts on the remote server via SSH. Scripts are defined as module-level string constants:

- `_LIST_DIRECTORIES_SCRIPT` - List folders in a directory
- `_LIST_FILES_SCRIPT` - List all entries with metadata
- `_DISK_USAGE_SCRIPT` - Disk usage and inode info
- `_LIST_BLOCK_DEVICES_SCRIPT` - Block device information
- `_DIRECTORY_STATS_SCRIPT` - Recursive directory statistics
- `_ENTRY_PROPERTIES_SCRIPT` - File/directory properties
- `_READ_FILE_SCRIPT` - Read file content (with base64 for binary)
- `_WRITE_FILE_SCRIPT` - Write file content

## Worker pattern

All blocking operations run in background threads via `_start_worker(operation)`. This prevents the UI from freezing. The pattern:

```python
def operation() -> None:
    # blocking work here
    self._set_connection_status("connected", "message")
    self.someSignal.emit(...)

self._start_worker(operation)
```

## Host key management

- Known hosts stored at `~/.deepzoom-cleaner/known_hosts`
- `HostKeyConfirmationRequired` exception raised for unknown host keys
- `acceptPendingHostKey()` / `rejectPendingHostKey()` slots for user confirmation
- `hostKeyTrustRequested` signal emitted when verification is needed

## Settings integration

Settings are managed in `deepzoom_cleaner/settings.py`:
- `load_settings()` / `save_settings(settings)` - JSON file at `~/.deepzoom-cleaner/settings.json`
- `get_ui_preference(key, default)` / `set_ui_preference(key, value)` - UI preferences
- `add_connection_to_history(...)` / `get_connection_history()` - Connection history
- `remove_connection_from_history(...)` - Remove connection

## Files to reference

- `deepzoom_cleaner/backend.py` - Main backend implementation
- `deepzoom_cleaner/settings.py` - Settings management
- `deepzoom_cleaner/session_manager.py` - Session management (multiple backends)