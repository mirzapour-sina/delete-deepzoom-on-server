import base64
import hashlib
import json
import posixpath
import shlex
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Optional

import paramiko
from PySide6.QtCore import QObject, QStandardPaths, QTimer, Property, Signal, Slot

from .settings import (
    load_settings,
    save_settings,
    add_connection_to_history,
    get_connection_history,
    get_last_connection,
    update_last_used,
    get_ui_preference,
    set_ui_preference,
)


_LIST_DIRECTORIES_SCRIPT = """\
import json
import os
import sys

root = os.path.abspath(sys.argv[1])
with os.scandir(root) as entries:
    folders = [
        {"name": entry.name, "path": os.path.join(root, entry.name)}
        for entry in entries
        if entry.is_dir(follow_symlinks=False)
    ]
print(json.dumps(folders, ensure_ascii=True))
"""


_LIST_FILES_SCRIPT = """\
import json
import os
import stat
import sys

root = os.path.abspath(sys.argv[1])
with os.scandir(root) as it:
    entries = []
    for entry in it:
        try:
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        entries.append({
            "name": entry.name,
            "path": os.path.join(root, entry.name),
            "is_dir": entry.is_dir(follow_symlinks=False),
            "is_link": entry.is_symlink(),
            "size": st.st_size,
            "mtime": st.st_mtime,
            "mode": stat.S_IMODE(st.st_mode),
        })
print(json.dumps(entries))
"""


_DISK_USAGE_SCRIPT = """\
import json
import shutil
import subprocess


def _run(argv):
    if shutil.which(argv[0]) is None:
        return ""
    try:
        result = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _rows(text):
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[1:]


def _parse_space(text):
    parsed = []
    for line in _rows(text):
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        device, size, used, available, capacity, mount = parts
        try:
            parsed.append({
                "device": device,
                "mount": mount,
                "size": int(size) * 1024,
                "used": int(used) * 1024,
                "available": int(available) * 1024,
                "used_percent": int(capacity.rstrip("%")),
            })
        except ValueError:
            continue
    return parsed


def _parse_inodes(text):
    parsed = []
    for line in _rows(text):
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        device, total, used, free, percent, mount = parts
        try:
            parsed.append({
                "device": device,
                "mount": mount,
                "inodes": int(total),
                "inodes_used": int(used),
                "inodes_free": int(free),
                "inodes_used_percent": int(percent.rstrip("%")),
            })
        except ValueError:
            continue
    return parsed


space = _parse_space(_run(["df", "-P", "-k"]))
inodes = _parse_inodes(_run(["df", "-P", "-i"]))
inode_by_mount = {row["mount"]: row for row in inodes}
inode_by_device = {row["device"]: row for row in inodes}

filesystems = []
for row in space:
    inodes_row = inode_by_mount.get(row["mount"]) or inode_by_device.get(row["device"])
    if inodes_row is None:
        inodes_row = {
            "inodes": 0,
            "inodes_used": 0,
            "inodes_free": 0,
            "inodes_used_percent": 0,
        }
    merged = dict(row)
    merged.update(inodes_row)
    filesystems.append(merged)

print(json.dumps(filesystems))
"""


_LIST_BLOCK_DEVICES_SCRIPT = """\
import json
import os
import shutil
import subprocess


def _run(argv):
    if shutil.which(argv[0]) is None:
        return ""
    try:
        result = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _flatten(nodes, parent, output):
    for node in nodes:
        name = node.get("name") or ""
        mount = node.get("mountpoint") or ""
        if not mount:
            for child in node.get("children") or []:
                mount = child.get("mountpoint") or ""
                if mount:
                    break
        size = node.get("size")
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = 0
        output.append({
            "name": name,
            "path": "/dev/" + name if name else "",
            "parent": parent,
            "type": node.get("type") or "",
            "size": size,
            "fstype": node.get("fstype") or "",
            "mount": mount,
            "label": node.get("label") or "",
            "uuid": node.get("uuid") or "",
            "model": (node.get("model") or "").strip(),
            "rotational": bool(node.get("rota")),
        })
        _flatten(node.get("children") or [], name, output)


devices = []
lsblk_output = _run([
    "lsblk", "-a", "-b", "-J",
    "-o", "NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,LABEL,UUID,MODEL,ROTA",
])

if lsblk_output:
    try:
        parsed = json.loads(lsblk_output)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict) and isinstance(parsed.get("blockdevices"), list):
        _flatten(parsed["blockdevices"], "", devices)

if not devices:
    sizes = {}
    try:
        with open("/proc/partitions") as handle:
            for line in handle.readlines()[2:]:
                parts = line.split()
                if len(parts) < 4:
                    continue
                try:
                    sizes[parts[3]] = int(parts[2]) * 1024
                except ValueError:
                    continue
    except OSError:
        sizes = {}

    mounts = {}
    try:
        with open("/proc/mounts") as handle:
            for line in handle.readlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                mounts[parts[0]] = parts[1]
    except OSError:
        mounts = {}

    for name, size in sorted(sizes.items()):
        kind = "part" if name[-1:].isdigit() else "disk"
        devices.append({
            "name": name,
            "path": "/dev/" + name,
            "parent": "",
            "type": kind,
            "size": size,
            "fstype": "",
            "mount": mounts.get("/dev/" + name, ""),
            "label": "",
            "uuid": "",
            "model": "",
            "rotational": False,
        })

print(json.dumps(devices))
"""


_DIRECTORY_STATS_SCRIPT = """\
import json
import os
import sys
import time

root = os.path.abspath(sys.argv[1])

file_count = 0
dir_count = 0
link_count = 0
other_count = 0
total_size = 0
error_count = 0
max_depth = 0

stack = [(root, 0)]
last_progress = time.monotonic()

while stack:
    path, depth = stack.pop()
    if depth > max_depth:
        max_depth = depth
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        link_count += 1
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        dir_count += 1
                        stack.append((entry.path, depth + 1))
                    else:
                        file_count += 1
                        try:
                            total_size += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            error_count += 1
                except OSError:
                    error_count += 1
    except OSError:
        error_count += 1

    now = time.monotonic()
    if now - last_progress >= 1.0:
        last_progress = now
        print(
            json.dumps({
                "path": root,
                "files": file_count,
                "directories": dir_count,
                "symlinks": link_count,
                "other": other_count,
                "total_size": total_size,
                "errors": error_count,
                "max_depth": max_depth,
                "progress": True,
            }),
            flush=True,
        )

print(json.dumps({
    "path": root,
    "files": file_count,
    "directories": dir_count,
    "symlinks": link_count,
    "other": other_count,
    "total_size": total_size,
    "errors": error_count,
    "max_depth": max_depth,
    "progress": False,
}))
"""


_ENTRY_PROPERTIES_SCRIPT = """\
import grp
import json
import os
import pwd
import stat
import sys

path = os.path.abspath(sys.argv[1])
try:
    st = os.lstat(path)
except OSError as exc:
    print(json.dumps({"error": str(exc)}))
    raise SystemExit(0)

mode = st.st_mode
if stat.S_ISLNK(mode):
    kind = "Symbolic link"
elif stat.S_ISDIR(mode):
    kind = "Folder"
elif stat.S_ISFIFO(mode):
    kind = "FIFO"
elif stat.S_ISSOCK(mode):
    kind = "Socket"
elif stat.S_ISBLK(mode):
    kind = "Block device"
elif stat.S_ISCHR(mode):
    kind = "Character device"
else:
    kind = "File"

info = {
    "path": path,
    "name": os.path.basename(path) or path,
    "kind": kind,
    "size": st.st_size,
    "mode": stat.filemode(mode),
    "octal_mode": oct(stat.S_IMODE(mode)),
    "uid": st.st_uid,
    "gid": st.st_gid,
    "links": st.st_nlink,
    "mtime": st.st_mtime,
    "atime": st.st_atime,
    "ctime": st.st_ctime,
    "device": st.st_dev,
    "inode": st.st_ino,
}

try:
    info["owner"] = pwd.getpwuid(st.st_uid).pw_name
except (KeyError, OSError):
    info["owner"] = str(st.st_uid)

try:
    info["group"] = grp.getgrgid(st.st_gid).gr_name
except (KeyError, OSError):
    info["group"] = str(st.st_gid)

if kind == "Symbolic link":
    try:
        info["target"] = os.readlink(path)
    except OSError:
        info["target"] = ""
    try:
        info["resolved"] = os.path.realpath(path)
    except OSError:
        info["resolved"] = ""


print(json.dumps(info))
"""


_READ_FILE_SCRIPT = """\
import base64
import json
import os
import sys

path = os.path.abspath(sys.argv[1])
max_size = int(sys.argv[2]) if len(sys.argv) > 2 else 10485760  # 10MB default

try:
    st = os.stat(path)
except OSError as exc:
    print(json.dumps({"error": str(exc)}))
    raise SystemExit(0)

if st.st_size > max_size:
    print(json.dumps({"error": f"File too large ({st.st_size} bytes), max {max_size} bytes"}))
    raise SystemExit(0)

try:
    with open(path, "rb") as f:
        content = f.read()
    # Try to decode as UTF-8
    try:
        text = content.decode("utf-8")
        is_binary = False
    except UnicodeDecodeError:
        text = base64.b64encode(content).decode("ascii")
        is_binary = True
    print(json.dumps({
        "content": text,
        "is_binary": is_binary,
        "size": st.st_size,
        "mtime": st.st_mtime,
    }))
except OSError as exc:
    print(json.dumps({"error": str(exc)}))
"""


_WRITE_FILE_SCRIPT = """\
import base64
import json
import os
import sys

path = os.path.abspath(sys.argv[1])
content_b64 = sys.argv[2] if len(sys.argv) > 2 else ""
is_binary = sys.argv[3].lower() == "true" if len(sys.argv) > 3 else False

try:
    # Decode content
    if is_binary:
        content = base64.b64decode(content_b64)
    else:
        content = content_b64.encode("utf-8")

    # Write file
    with open(path, "wb") as f:
        f.write(content)

    print(json.dumps({"success": True, "size": len(content)}))
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
"""


ARCHIVE_FORMATS: dict[str, dict[str, Any]] = {
    "tar.gz": {
        "extension": ".tar.gz",
        "create_tools": ("tar",),
        "create": "{tool} -czf {archive} {items}",
        "extract_tools": ("tar",),
        "extract": "{tool} -xzf {archive} -C {dest}",
    },
    "tar.bz2": {
        "extension": ".tar.bz2",
        "create_tools": ("tar",),
        "create": "{tool} -cjf {archive} {items}",
        "extract_tools": ("tar",),
        "extract": "{tool} -xjf {archive} -C {dest}",
    },
    "tar.xz": {
        "extension": ".tar.xz",
        "create_tools": ("tar",),
        "create": "{tool} -cJf {archive} {items}",
        "extract_tools": ("tar",),
        "extract": "{tool} -xJf {archive} -C {dest}",
    },
    "zip": {
        "extension": ".zip",
        "create_tools": ("zip",),
        "create": "{tool} -r {archive} {items}",
        "extract_tools": ("unzip",),
        "extract": "{tool} {archive} -d {dest}",
    },
    "7z": {
        "extension": ".7z",
        "create_tools": ("7z", "7zz", "7za"),
        "create": "{tool} a {archive} {items}",
        "extract_tools": ("7z", "7zz", "7za"),
        "extract": "{tool} x {archive} -o{dest}",
    },
    "rar": {
        "extension": ".rar",
        "create_tools": ("rar",),
        "create": "{tool} a {archive} {items}",
        "extract_tools": ("unrar", "rar"),
        "extract": "{tool} x {archive} {dest}",
    },
}

ARCHIVE_EXTENSIONS: tuple[tuple[str, str], ...] = (
    (".tar.gz", "tar.gz"),
    (".tgz", "tar.gz"),
    (".tar.bz2", "tar.bz2"),
    (".tbz2", "tar.bz2"),
    (".tar.xz", "tar.xz"),
    (".txz", "tar.xz"),
    (".zip", "zip"),
    (".7z", "7z"),
    (".rar", "rar"),
)


def detect_archive_format(name: str) -> str | None:
    lower = name.lower()
    for suffix, format_name in ARCHIVE_EXTENSIONS:
        if lower.endswith(suffix):
            return format_name
    return None


def _normalize_remote_path(path: str) -> str:
    normalized = posixpath.normpath(path)
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized


def _is_same_or_descendant(path: str, ancestor: str) -> bool:
    ancestor = ancestor.rstrip("/") or "/"
    if ancestor == "/":
        return path.startswith("/")
    return path == ancestor or path.startswith(ancestor + "/")


class HostKeyConfirmationRequired(Exception):
    def __init__(self, hostname: str, key: paramiko.PKey) -> None:
        super().__init__(hostname)
        self.hostname = hostname
        self.key = key


class _ConfirmMissingHostKey(paramiko.MissingHostKeyPolicy):
    def missing_host_key(
        self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey
    ) -> None:
        raise HostKeyConfirmationRequired(hostname, key)


class Backend(QObject):
    busyChanged = Signal(bool)
    entriesLoaded = Signal(str, list)
    errorOccurred = Signal(str)
    foldersLoaded = Signal(list)
    folderContentsLoaded = Signal(str, list)  # path, entries (tree children, no main-view navigation)
    foldersRemoved = Signal(list)
    hostKeyTrustRequested = Signal(str, int, str)
    clipboardChanged = Signal(str, int)
    statusChanged = Signal(str)
    diskUsageLoaded = Signal(list)
    blockDevicesLoaded = Signal(list)
    directoryStatsLoaded = Signal(str, dict)
    directoryStatsProgress = Signal(str, int, int)  # path, files, directories
    entryPropertiesLoaded = Signal(str, dict)
    entryStatsLoaded = Signal(str, dict)  # path, {files_inside, folders_inside}
    entryStatsProgress = Signal(str, int, int)  # path, files_inside, folders_inside
    connectionStatusChanged = Signal(str, str)  # status, message
    connectionHistoryLoaded = Signal(list)  # list of connection profiles
    connectionSaved = Signal(str)  # host:port
    connectionRemoved = Signal(str)  # host:port
    # File editor signals
    fileContentLoaded = Signal(str, dict)  # path, info dict with content, is_binary, size, mtime
    fileWritten = Signal(str, bool, str)  # path, success, message
    # Upload/Download signals
    uploadProgress = Signal(str, int, int)  # filename, current, total
    downloadProgress = Signal(str, int, int)  # filename, current, total
    uploadCompleted = Signal(str, bool, str)  # remote_path, success, message
    downloadCompleted = Signal(str, bool, str)  # local_path, success, message

    def __init__(self) -> None:
        super().__init__()
        self._busy = False
        self._settings: dict[str, Any] | None = None
        self._listed_paths: set[str] = set()
        self._workers: set[threading.Thread] = set()
        self._pending_host_key: tuple[dict[str, Any], HostKeyConfirmationRequired] | None = None
        self._current_path: str | None = None
        self._current_entries: dict[str, dict[str, Any]] = {}
        self._clipboard_operation = ""
        self._clipboard_paths: list[str] = []
        self._connection_status = "disconnected"
        self._connection_message = "Not connected"
        self._download_cancelled = threading.Event()
        self._connection_history: list[dict] = []

        # Load connection history on startup
        self._load_connection_history()

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        """True while a background operation is running.

        Exposed as a property so QML can bind to ``backend.busy`` and update
        automatically when the signal fires.
        """
        return self._busy

    def _load_connection_history(self) -> None:
        """Load connection history and emit signal."""
        try:
            history = get_connection_history()
            # Add displayText property for ComboBox
            for item in history:
                host = item.get("host", "")
                port = item.get("port", 22)
                username = item.get("username", "")
                remote_path = item.get("remote_path", "")
                item["displayText"] = f"{host}:{port} ({username}@{remote_path})"
            self._connection_history = history
            self.connectionHistoryLoaded.emit(history)
        except Exception as exc:
            self.errorOccurred.emit(f"Failed to load connection history: {exc}")

    def _set_connection_status(self, status: str, message: str) -> None:
        """Update connection status and emit signal."""
        self._connection_status = status
        self._connection_message = message
        self.connectionStatusChanged.emit(status, message)

    @property
    def connection_status(self) -> str:
        return self._connection_status

    @property
    def connection_message(self) -> str:
        return self._connection_message

    @Slot(result=bool)
    def showHiddenFiles(self) -> bool:
        """Return whether hidden files should be shown by default."""
        return bool(get_ui_preference("show_hidden_files", False))

    @Slot(bool)
    def setShowHiddenFiles(self, value: bool) -> None:
        """Persist the show-hidden-files preference."""
        set_ui_preference("show_hidden_files", value)

    @Slot(result="QVariant")
    def getTheme(self) -> str:
        """Return the current UI theme preference ("light", "dark", or "system")."""
        return str(get_ui_preference("theme", "system"))

    @Slot(str)
    def setTheme(self, theme: str) -> None:
        """Persist the UI theme preference."""
        set_ui_preference("theme", theme)

    @Slot(result="QVariant")
    def getLastConnection(self) -> dict:
        """Return the last used connection profile for pre-filling the form."""
        return get_last_connection() or {}

    @Slot(result="QVariantList")
    def getConnectionHistory(self) -> list[dict]:
        """Return the cached connection history synchronously."""
        return list(self._connection_history)

    @Slot(str, str, str, str, str, str, bool)
    def connectAndLoad(
        self,
        host: str,
        username: str,
        port_text: str,
        remote_path: str,
        key_filename: str,
        password: str,
        save_password: bool = False,
    ) -> None:
        try:
            port = int(port_text)
        except ValueError:
            self.errorOccurred.emit("Port must be a number between 1 and 65535.")
            return
        if not 1 <= port <= 65535:
            self.errorOccurred.emit("Port must be a number between 1 and 65535.")
            return
        if not host.strip() or not username.strip():
            self.errorOccurred.emit("Enter both a server address and username.")
            return
        if not remote_path.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return

        settings = {
            "host": host.strip(),
            "username": username.strip(),
            "port": port,
            "remote_path": remote_path,
            "key_filename": key_filename.strip() or None,
            "password": password or None,
        }
        if self._busy:
            self.errorOccurred.emit("Please wait for the current operation to finish.")
            return
        self._pending_host_key = None
        self._listed_paths.clear()
        self.foldersLoaded.emit([])

        def operation() -> None:
            self._set_connection_status("connecting", "Connecting to server…")
            self.statusChanged.emit("Connecting and reading remote folders…")
            try:
                client = self._open_client(settings)
            except HostKeyConfirmationRequired as exc:
                self._pending_host_key = (settings, exc)
                self.hostKeyTrustRequested.emit(
                    settings["host"],
                    settings["port"],
                    self._fingerprint(exc.key),
                )
                self._set_connection_status("host_key_required", "Server identity needs verification")
                self.statusChanged.emit(
                    "Server identity needs verification before connecting."
                )
                return
            except paramiko.BadHostKeyException as exc:
                fingerprint = self._fingerprint(exc.key)
                self._set_connection_status("disconnected", f"Host key changed: {fingerprint}")
                self.errorOccurred.emit(
                    "The server's SSH host key has changed from the trusted key. "
                    f"Connection refused. Reported fingerprint: {fingerprint}"
                )
                self.statusChanged.emit("Server identity check failed.")
                return
            except Exception as exc:
                self._set_connection_status("disconnected", f"Connection failed: {exc}")
                self.errorOccurred.emit(f"Connection failed: {exc}")
                self.statusChanged.emit("Connection failed.")
                return
            try:
                folders = self._list_folders(client, remote_path)
                entries = self._list_entries(client, remote_path)
            finally:
                client.close()
            self._settings = settings
            self._listed_paths = {folder["path"] for folder in folders}
            self._current_path = remote_path
            self._current_entries = {entry["path"]: entry for entry in entries}
            self._clear_clipboard()
            self.foldersLoaded.emit(folders)
            self.entriesLoaded.emit(remote_path, entries)

            # Save to history and update status
            add_connection_to_history(
                host=settings["host"],
                username=settings["username"],
                port=settings["port"],
                remote_path=settings["remote_path"],
                key_filename=settings["key_filename"],
                save_password=save_password,
                password=settings["password"] if save_password else None,
            )
            update_last_used(settings["host"], settings["username"], settings["port"], settings["remote_path"])
            self._load_connection_history()

            host_key = f"{settings['host']}:{settings['port']}"
            self.connectionSaved.emit(host_key)
            self._set_connection_status("connected", f"Connected to {host_key}")
            self.statusChanged.emit(
                f"Loaded {len(folders)} folders from "
                f"{settings['host']}:{remote_path}."
            )

        self._start_worker(operation)

    @Slot()
    def acceptPendingHostKey(self) -> None:
        pending = self._pending_host_key
        if pending is None:
            self.errorOccurred.emit("There is no server key waiting for approval.")
            return
        if self._busy:
            QTimer.singleShot(100, self.acceptPendingHostKey)
            return

        settings, host_key = pending
        try:
            self._store_host_key(host_key.hostname, host_key.key)
        except (OSError, paramiko.SSHException) as exc:
            self.errorOccurred.emit(f"Could not save the trusted server key: {exc}")
            return

        self._pending_host_key = None
        self.statusChanged.emit("Server key trusted. Reconnecting…")
        self.connectAndLoad(
            settings["host"],
            settings["username"],
            str(settings["port"]),
            settings["remote_path"],
            settings["key_filename"] or "",
            settings["password"] or "",
        )

    @Slot()
    def rejectPendingHostKey(self) -> None:
        if self._pending_host_key is not None:
            self._pending_host_key = None
            self.statusChanged.emit("Server key was not trusted; connection cancelled.")
            self._set_connection_status("disconnected", "Connection cancelled.")

    @Slot()
    def loadConnectionHistory(self) -> None:
        """Reload and emit connection history."""
        self._load_connection_history()

    @Slot(str, str, int, str)
    def loadConnectionProfile(self, host: str, username: str, port: int, remote_path: str) -> None:
        """Load a saved connection profile and connect."""
        settings = load_settings()
        history = settings.get("connection_history", [])
        for profile in history:
            if (profile.get("host") == host and
                profile.get("username") == username and
                profile.get("port") == port and
                profile.get("remote_path") == remote_path):
                # Found the profile, connect with saved credentials
                key_filename = profile.get("key_filename") or ""
                password = profile.get("password") or ""
                self.connectAndLoad(
                    host,
                    username,
                    str(port),
                    remote_path,
                    key_filename,
                    password,
                )
                return
        self.errorOccurred.emit("Connection profile not found in history.")

    @Slot(str, str, int, str)
    def removeConnectionFromHistory(self, host: str, username: str, port: int, remote_path: str) -> None:
        """Remove a connection from history."""
        from .settings import remove_connection_from_history
        if remove_connection_from_history(host, username, port, remote_path):
            self._load_connection_history()
            host_key = f"{host}:{port}"
            self.connectionRemoved.emit(host_key)
            self.statusChanged.emit("Connection removed from history.")
        else:
            self.errorOccurred.emit("Connection profile not found in history.")

    @Slot()
    def disconnect(self) -> None:
        """Disconnect from current server."""
        self._settings = None
        self._listed_paths.clear()
        self._current_path = None
        self._current_entries.clear()
        self._clear_clipboard()
        self.foldersLoaded.emit([])
        self.entriesLoaded.emit("", [])
        self._set_connection_status("disconnected", "Disconnected")
        self.statusChanged.emit("Disconnected from server.")

    @Slot("QVariantList")
    def removeFolders(self, selected_paths: list[str]) -> None:
        if not selected_paths:
            self.errorOccurred.emit("Select at least one folder to remove.")
            return
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server and load folders first.")
            return

        # Only allow removal of folders returned by the most recent listing.
        if any(path not in self._listed_paths for path in selected_paths):
            self.errorOccurred.emit("The selection is out of date. Reload the folder list before deleting.")
            return
        if len(set(selected_paths)) != len(selected_paths):
            self.errorOccurred.emit("The selection contains duplicate folders.")
            return

        settings = self._settings.copy()
        paths = list(selected_paths)

        def operation() -> None:
            self.statusChanged.emit(f"Removing {len(paths)} folders on the server…")
            client = self._open_client(settings)
            removed: list[str] = []
            failures: list[str] = []
            try:
                worker_count = min(4, len(paths))
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    futures = {
                        executor.submit(self._remove_one, client, path): path
                        for path in paths
                    }
                    completed = 0
                    for future in as_completed(futures):
                        path = futures[future]
                        completed += 1
                        try:
                            future.result()
                            removed.append(path)
                        except Exception as exc:
                            failures.append(f"{path}: {exc}")
                        self.statusChanged.emit(
                            f"Finished {completed} of {len(paths)} selected folders."
                        )
                current = self._current_path
                entries = (
                    self._list_entries(client, current)
                    if current == settings["remote_path"]
                    else None
                )
            finally:
                client.close()

            if entries is not None:
                self._publish_entries(current, entries)
            if removed:
                self._listed_paths.difference_update(removed)
                self.foldersRemoved.emit(removed)
            if failures:
                self.errorOccurred.emit(
                    "Some folders could not be removed:\n" + "\n".join(failures)
                )
                self.statusChanged.emit(
                    f"Removed {len(removed)} of {len(paths)} folders; some failed."
                )
            else:
                self.statusChanged.emit(f"Successfully removed {len(removed)} folders.")

        self._start_worker(operation)

    # -- File explorer -----------------------------------------------------

    @Slot(str)
    def navigate(self, path: str) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        cleaned = path.strip()
        if not cleaned.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return
        target = _normalize_remote_path(cleaned)
        settings = self._settings.copy()

        def operation() -> None:
            self.statusChanged.emit(f"Reading {target}…")
            client = self._open_client(settings)
            try:
                entries = self._list_entries(client, target)
            finally:
                client.close()
            self._publish_entries(target, entries)
            self.statusChanged.emit(f"{len(entries)} entries in {target}.")

        self._start_worker(operation)

    @Slot(str)
    def listFolderContents(self, path: str) -> None:
        """List entries of a folder without changing the current view (for tree expansion)."""
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        cleaned = path.strip()
        if not cleaned.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return
        target = _normalize_remote_path(cleaned)
        settings = self._settings.copy()

        def operation() -> None:
            self.statusChanged.emit(f"Reading {target}…")
            client = self._open_client(settings)
            try:
                entries = self._list_entries(client, target)
            finally:
                client.close()
            self.folderContentsLoaded.emit(target, entries)

        self._start_worker(operation)

    @Slot()
    def refresh(self) -> None:
        if self._current_path is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        self.navigate(self._current_path)

    @Slot("QVariantList")
    def copySelection(self, paths: list[str]) -> None:
        self._set_clipboard("copy", paths)

    @Slot("QVariantList")
    def cutSelection(self, paths: list[str]) -> None:
        self._set_clipboard("cut", paths)

    @Slot()
    def clearClipboard(self) -> None:
        self._clear_clipboard()
        self.statusChanged.emit("Clipboard cleared.")

    def _set_clipboard(self, operation: str, paths: list[str]) -> None:
        if not paths:
            self.errorOccurred.emit("Select at least one item first.")
            return
        if any(path not in self._current_entries for path in paths):
            self.errorOccurred.emit(
                "The selection is out of date. Refresh the folder first."
            )
            return
        self._clipboard_operation = operation
        self._clipboard_paths = list(dict.fromkeys(paths))
        self.clipboardChanged.emit(operation, len(self._clipboard_paths))
        verb = "copy" if operation == "copy" else "move"
        self.statusChanged.emit(
            f"{len(self._clipboard_paths)} item(s) ready to {verb}."
        )

    def _clear_clipboard(self) -> None:
        self._clipboard_operation = ""
        self._clipboard_paths = []
        self.clipboardChanged.emit("", 0)

    @Slot(str)
    def pasteInto(self, destination: str) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        if not self._clipboard_paths:
            self.errorOccurred.emit("The clipboard is empty.")
            return
        cleaned = destination.strip()
        if not cleaned.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return
        dest = _normalize_remote_path(cleaned)
        sources = list(self._clipboard_paths)
        move = self._clipboard_operation == "cut"
        settings = self._settings.copy()

        def operation() -> None:
            verb = "Moving" if move else "Copying"
            self.statusChanged.emit(f"{verb} {len(sources)} item(s) to {dest}…")
            client = self._open_client(settings)
            try:
                for source in sources:
                    if _is_same_or_descendant(dest, source):
                        raise RuntimeError(
                            f"Cannot paste {posixpath.basename(source)} into itself "
                            "or a folder inside it."
                        )
                existing = {entry["name"] for entry in self._list_entries(client, dest)}
                conflicts = [
                    posixpath.basename(source)
                    for source in sources
                    if posixpath.basename(source) in existing
                ]
                if conflicts:
                    raise RuntimeError(
                        "The destination already contains: "
                        + ", ".join(conflicts)
                        + ". Rename or remove those items before pasting."
                    )
                for index, source in enumerate(sources, start=1):
                    self._run_remote(
                        client, self._transfer_command(
                            [source], dest, move
                        )
                    )
                    self.statusChanged.emit(
                        f"Finished {index} of {len(sources)} item(s)."
                    )
                entries = self._list_entries(client, dest)
                if move:
                    self.foldersRemoved.emit([source for source in sources])
            finally:
                client.close()
            if move:
                self._clear_clipboard()
            self._publish_entries(dest, entries)
            self.statusChanged.emit(
                f"{'Moved' if move else 'Copied'} {len(sources)} item(s) to {dest}."
            )

        self._start_worker(operation)

    @Slot("QVariantList")
    def deleteSelection(self, paths: list[str]) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        if not paths:
            self.errorOccurred.emit("Select at least one item to remove.")
            return
        if any(path not in self._current_entries for path in paths):
            self.errorOccurred.emit(
                "The selection is out of date. Refresh the folder first."
            )
            return
        settings = self._settings.copy()
        targets = list(dict.fromkeys(paths))

        def operation() -> None:
            self.statusChanged.emit(f"Removing {len(targets)} item(s) on the server…")
            client = self._open_client(settings)
            removed: list[str] = []
            failures: list[str] = []
            try:
                with ThreadPoolExecutor(max_workers=min(4, len(targets))) as executor:
                    futures = {
                        executor.submit(self._remove_one, client, path): path
                        for path in targets
                    }
                    completed = 0
                    for future in as_completed(futures):
                        path = futures[future]
                        completed += 1
                        try:
                            future.result()
                            removed.append(path)
                        except Exception as exc:
                            failures.append(f"{path}: {exc}")
                        self.statusChanged.emit(
                            f"Finished {completed} of {len(targets)} item(s)."
                        )
                current = self._current_path or posixpath.dirname(targets[0])
                entries = self._list_entries(client, current)
            finally:
                client.close()

            self._publish_entries(current, entries)
            if removed:
                self.foldersRemoved.emit(removed)
            if failures:
                self.errorOccurred.emit(
                    "Some items could not be removed:\n" + "\n".join(failures)
                )
                self.statusChanged.emit(
                    f"Removed {len(removed)} of {len(targets)} item(s); some failed."
                )
            else:
                self.statusChanged.emit(f"Removed {len(removed)} item(s).")

        self._start_worker(operation)

    @Slot(str, str)
    def renameEntry(self, path: str, new_name: str) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        if path not in self._current_entries:
            self.errorOccurred.emit(
                "The selection is out of date. Refresh the folder first."
            )
            return
        cleaned = new_name.strip()
        problem = self._validate_entry_name(cleaned, "name")
        if problem:
            self.errorOccurred.emit(problem)
            return
        new_path = posixpath.join(posixpath.dirname(path), cleaned)
        if new_path in self._current_entries:
            self.errorOccurred.emit(f"An item named '{cleaned}' already exists.")
            return
        settings = self._settings.copy()

        def operation() -> None:
            self.statusChanged.emit(f"Renaming {posixpath.basename(path)}…")
            client = self._open_client(settings)
            try:
                self._run_remote(
                    client,
                    f"mv -- {shlex.quote(path)} {shlex.quote(new_path)}",
                )
                current = self._current_path or posixpath.dirname(path)
                entries = self._list_entries(client, current)
            finally:
                client.close()
            self._publish_entries(current, entries)
            self.statusChanged.emit(f"Renamed to '{cleaned}'.")

        self._start_worker(operation)

    @Slot(str, str)
    def createDirectory(self, parent: str, name: str) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        cleaned = name.strip()
        problem = self._validate_entry_name(cleaned, "folder name")
        if problem:
            self.errorOccurred.emit(problem)
            return
        if not parent.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return
        new_path = posixpath.join(_normalize_remote_path(parent), cleaned)
        settings = self._settings.copy()

        def operation() -> None:
            self.statusChanged.emit(f"Creating folder '{cleaned}'…")
            client = self._open_client(settings)
            try:
                self._run_remote(client, f"mkdir -- {shlex.quote(new_path)}")
                current = self._current_path or parent
                entries = self._list_entries(client, current)
            finally:
                client.close()
            self._publish_entries(current, entries)
            self.statusChanged.emit(f"Created folder '{cleaned}'.")

        self._start_worker(operation)

    @Slot("QVariantList", str, str)
    def compressSelection(
        self, paths: list[str], archive_name: str, format_name: str
    ) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        if not paths:
            self.errorOccurred.emit("Select at least one item to compress.")
            return
        if any(path not in self._current_entries for path in paths):
            self.errorOccurred.emit(
                "The selection is out of date. Refresh the folder first."
            )
            return
        if format_name not in ARCHIVE_FORMATS:
            self.errorOccurred.emit("Choose a supported archive format.")
            return
        parents = {posixpath.dirname(path) for path in paths}
        if len(parents) != 1:
            self.errorOccurred.emit("All selected items must be in the same folder.")
            return
        parent = parents.pop()
        cleaned = archive_name.strip()
        problem = self._validate_entry_name(cleaned, "archive name")
        if problem:
            self.errorOccurred.emit(problem)
            return
        extension = str(ARCHIVE_FORMATS[format_name]["extension"])
        if not cleaned.lower().endswith(extension):
            cleaned += extension
        nearby_names = {
            entry["name"]
            for entry in self._current_entries.values()
            if posixpath.dirname(entry["path"]) == parent
        }
        if cleaned in nearby_names:
            self.errorOccurred.emit(f"An item named '{cleaned}' already exists.")
            return
        names = [self._current_entries[path]["name"] for path in paths]
        settings = self._settings.copy()

        def operation() -> None:
            self.statusChanged.emit(f"Creating '{cleaned}' from {len(names)} item(s)…")
            client = self._open_client(settings)
            try:
                tool = self._require_tool(
                    client, tuple(ARCHIVE_FORMATS[format_name]["create_tools"])
                )
                self._run_remote(
                    client,
                    self._archive_create_command(
                        parent, cleaned, names, format_name, tool
                    ),
                )
                current = self._current_path or parent
                entries = self._list_entries(client, current)
            finally:
                client.close()
            self._publish_entries(current, entries)
            self.statusChanged.emit(f"Created '{cleaned}'.")

        self._start_worker(operation)

    @Slot(str, str)
    def extractArchive(self, archive_path: str, destination: str) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        entry = self._current_entries.get(archive_path)
        if entry is None:
            self.errorOccurred.emit(
                "The selection is out of date. Refresh the folder first."
            )
            return
        if entry["is_dir"]:
            self.errorOccurred.emit("Select an archive file to extract.")
            return
        archive_name = entry["name"]
        format_name = detect_archive_format(archive_name)
        if format_name is None:
            self.errorOccurred.emit(
                "Only .tar.gz, .tar.bz2, .tar.xz, .zip, .7z and .rar archives "
                "can be extracted."
            )
            return
        parent = posixpath.dirname(archive_path)
        stem = archive_name
        for suffix, detected in ARCHIVE_EXTENSIONS:
            if detected == format_name and archive_name.lower().endswith(suffix):
                stem = archive_name[: -len(suffix)]
                break
        cleaned = destination.strip()
        if cleaned.startswith("/"):
            target_dir = _normalize_remote_path(cleaned)
        else:
            folder_name = cleaned or stem
            problem = self._validate_entry_name(folder_name, "destination folder")
            if problem:
                self.errorOccurred.emit(problem)
                return
            target_dir = posixpath.join(parent, folder_name)
        settings = self._settings.copy()

        def operation() -> None:
            self.statusChanged.emit(f"Extracting '{archive_name}'…")
            client = self._open_client(settings)
            try:
                tool = self._require_tool(
                    client, tuple(ARCHIVE_FORMATS[format_name]["extract_tools"])
                )
                command = (
                    "mkdir -p -- "
                    + shlex.quote(target_dir)
                    + " && "
                    + self._archive_extract_command(
                        archive_path, target_dir, format_name, tool
                    )
                )
                self._run_remote(client, command)
                entries = self._list_entries(client, target_dir)
            finally:
                client.close()
            self._publish_entries(target_dir, entries)
            self.statusChanged.emit(f"Extracted '{archive_name}' to {target_dir}.")

        self._start_worker(operation)

    def _publish_entries(self, path: str, entries: list[dict[str, Any]]) -> None:
        self._current_path = path
        self._current_entries = {entry["path"]: entry for entry in entries}
        self.entriesLoaded.emit(path, entries)
        if self._settings is not None and path == self._settings["remote_path"]:
            folders = [
                {"name": entry["name"], "path": entry["path"]}
                for entry in entries
                if entry["is_dir"]
            ]
            self._listed_paths = {folder["path"] for folder in folders}
            self.foldersLoaded.emit(folders)

    @Slot()
    def loadDiskUsage(self) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        settings = self._settings.copy()

        def operation() -> None:
            client = self._open_client(settings)
            try:
                self.diskUsageLoaded.emit(
                    self._list_disk_usage(client)
                )
                self.statusChanged.emit("Disk usage loaded.")
            finally:
                client.close()

        self._start_worker(operation)

    @Slot()
    def loadBlockDevices(self) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        settings = self._settings.copy()

        def operation() -> None:
            client = self._open_client(settings)
            try:
                self.blockDevicesLoaded.emit(
                    self._list_block_devices(client)
                )
                self.statusChanged.emit("Block devices loaded.")
            finally:
                client.close()

        self._start_worker(operation)

    @Slot(str)
    def loadDirectoryStats(self, path: str) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        cleaned = path.strip()
        if not cleaned.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return
        target = _normalize_remote_path(cleaned)
        settings = self._settings.copy()

        def operation() -> None:
            client = None
            try:
                client = self._open_client(settings)
                self.statusChanged.emit(f"Calculating directory stats for {target}…")
                command = (
                    "python3 -c "
                    + shlex.quote(_DIRECTORY_STATS_SCRIPT)
                    + " "
                    + shlex.quote(target)
                )
                _, stdout, stderr = client.exec_command(command, get_pty=False)
                stdout.channel.settimeout(1.0)
                final_stats = None
                try:
                    while True:
                        try:
                            line = stdout.readline()
                        except socket.timeout:
                            if stdout.channel.exit_status_ready():
                                break
                            continue
                        if not line:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if data.get("progress"):
                            self.directoryStatsProgress.emit(
                                target,
                                int(data.get("files", 0)),
                                int(data.get("directories", 0)),
                            )
                        else:
                            final_stats = data
                finally:
                    try:
                        remaining = stdout.read().decode("utf-8", errors="replace")
                        if remaining.strip():
                            for remaining_line in remaining.strip().splitlines():
                                remaining_line = remaining_line.strip()
                                if not remaining_line:
                                    continue
                                try:
                                    data = json.loads(remaining_line)
                                    if not data.get("progress"):
                                        final_stats = data
                                except json.JSONDecodeError:
                                    pass
                    except Exception:
                        pass
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass
            stats = final_stats if isinstance(final_stats, dict) else {}
            self.directoryStatsLoaded.emit(target, stats)
            self.statusChanged.emit(
                f"{target}: {stats.get('files', 0)} file(s), "
                f"{stats.get('directories', 0)} folder(s) including subfolders."
            )

        self._start_worker(operation, busy=False)

    @Slot(str)
    def loadEntryProperties(self, path: str) -> None:
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        cleaned = path.strip()
        if not cleaned.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return
        target = _normalize_remote_path(cleaned)
        settings = self._settings.copy()

        def operation() -> None:
            client = self._open_client(settings)
            try:
                result = self._run_remote(
                    client,
                    "python3 -c "
                    + shlex.quote(_ENTRY_PROPERTIES_SCRIPT)
                    + " "
                    + shlex.quote(target),
                )
                info = json.loads(result) if result.strip() else {"error": "Empty response"}
            finally:
                client.close()
            self.entryPropertiesLoaded.emit(target, info)

        self._start_worker(operation)

    @Slot(str)
    def loadEntryStats(self, path: str) -> None:
        """Recursively count files and folders inside the given folder path.

        Emits entryStatsLoaded(path, {"files_inside": int, "folders_inside": int}).
        Invoked on demand from the properties dialog so that opening properties
        stays fast for large directory trees.
        """
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        cleaned = path.strip()
        if not cleaned.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return
        target = _normalize_remote_path(cleaned)
        settings = self._settings.copy()

        def operation() -> None:
            client = None
            try:
                client = self._open_client(settings)
                self.statusChanged.emit(f"Counting contents of {target}…")
                command = (
                    "python3 -c "
                    + shlex.quote(_DIRECTORY_STATS_SCRIPT)
                    + " "
                    + shlex.quote(target)
                )
                _, stdout, stderr = client.exec_command(command, get_pty=False)
                stdout.channel.settimeout(1.0)
                final_stats = None
                try:
                    while True:
                        try:
                            line = stdout.readline()
                        except socket.timeout:
                            if stdout.channel.exit_status_ready():
                                break
                            continue
                        if not line:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if data.get("progress"):
                            self.entryStatsProgress.emit(
                                target,
                                int(data.get("files", 0)),
                                int(data.get("directories", 0)),
                            )
                        else:
                            final_stats = data
                finally:
                    try:
                        remaining = stdout.read().decode("utf-8", errors="replace")
                        if remaining.strip():
                            for remaining_line in remaining.strip().splitlines():
                                remaining_line = remaining_line.strip()
                                if not remaining_line:
                                    continue
                                try:
                                    data = json.loads(remaining_line)
                                    if not data.get("progress"):
                                        final_stats = data
                                except json.JSONDecodeError:
                                    pass
                    except Exception:
                        pass
                    client.close()
                    client = None
                if final_stats:
                    self.entryStatsLoaded.emit(
                        target,
                        {
                            "files_inside": final_stats.get("files", 0),
                            "folders_inside": final_stats.get("directories", 0),
                        },
                    )
                    self.statusChanged.emit(
                        f"{target}: {final_stats.get('files', 0)} file(s), "
                        f"{final_stats.get('directories', 0)} folder(s) including subfolders."
                    )
            except Exception as exc:  # noqa: BLE001
                self.errorOccurred.emit(str(exc))
            finally:
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass

        self._start_worker(operation, busy=False)

    # -- File editor -------------------------------------------------------

    @Slot(str)
    def readFileContent(self, path: str) -> None:
        """Read a file from the server and emit fileContentLoaded signal."""
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        cleaned = path.strip()
        if not cleaned.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return
        target = _normalize_remote_path(cleaned)
        settings = self._settings.copy()

        def operation() -> None:
            self.statusChanged.emit(f"Reading file {target}…")
            client = self._open_client(settings)
            try:
                result = self._run_remote(
                    client,
                    "python3 -c "
                    + shlex.quote(_READ_FILE_SCRIPT)
                    + " "
                    + shlex.quote(target)
                    + " 10485760",  # 10MB max
                )
                info = json.loads(result) if result.strip() else {"error": "Empty response"}
            finally:
                client.close()
            self.fileContentLoaded.emit(target, info)
            if "error" in info:
                self.statusChanged.emit(f"Failed to read file: {info['error']}")
            else:
                size_kb = info.get("size", 0) / 1024
                self.statusChanged.emit(f"Loaded {target} ({size_kb:.1f} KB)")

        self._start_worker(operation)

    @Slot(str, str, bool)
    def writeFileContent(self, path: str, content_b64: str, is_binary: bool) -> None:
        """Write a file to the server and emit fileWritten signal."""
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        cleaned = path.strip()
        if not cleaned.startswith("/"):
            self.errorOccurred.emit("Enter an absolute Linux folder path (starting with /).")
            return
        target = _normalize_remote_path(cleaned)
        settings = self._settings.copy()

        def operation() -> None:
            self.statusChanged.emit(f"Writing file {target}…")
            client = self._open_client(settings)
            try:
                result = self._run_remote(
                    client,
                    "python3 -c "
                    + shlex.quote(_WRITE_FILE_SCRIPT)
                    + " "
                    + shlex.quote(target)
                    + " "
                    + shlex.quote(content_b64)
                    + " "
                    + shlex.quote(str(is_binary).lower()),
                )
                info = json.loads(result) if result.strip() else {"error": "Empty response"}
            finally:
                client.close()
            success = info.get("success", False)
            message = info.get("error", "File written successfully") if not success else "File written successfully"
            self.fileWritten.emit(target, success, message)
            if success:
                self.statusChanged.emit(f"Saved {target} ({info.get('size', 0)} bytes)")
                # Refresh the current directory to show updated file
                if self._current_path:
                    try:
                        client = self._open_client(settings)
                        entries = self._list_entries(client, self._current_path)
                        client.close()
                        self._publish_entries(self._current_path, entries)
                    except Exception:
                        pass
            else:
                self.statusChanged.emit(f"Failed to write file: {message}")

        self._start_worker(operation)

    # -- Upload/Download ---------------------------------------------------

    @Slot(result=str)
    def defaultDownloadDir(self) -> str:
        """Return the local folder downloads default to."""
        try:
            location = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.DownloadLocation
            )
        except Exception:
            location = ""
        if not location:
            location = str(Path.home() / "Downloads")
        return location

    @Slot(str, str)
    def uploadFile(self, local_path: str, remote_path: str) -> None:
        """Upload a local file to the server via SFTP."""
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        if not local_path or not remote_path:
            self.errorOccurred.emit("Both local and remote paths are required.")
            return
        if not remote_path.startswith("/"):
            self.errorOccurred.emit("Remote path must be absolute (starting with /).")
            return
        remote_path = _normalize_remote_path(remote_path)
        settings = self._settings.copy()

        def operation() -> None:
            local_file = Path(local_path)
            if not local_file.exists() or not local_file.is_file():
                self.uploadCompleted.emit(remote_path, False, f"Local file not found: {local_path}")
                return

            file_size = local_file.stat().st_size
            filename = local_file.name

            self.statusChanged.emit(f"Uploading {filename} ({file_size} bytes)…")
            self.uploadProgress.emit(filename, 0, file_size)

            client = self._open_client(settings)
            sftp = None
            try:
                sftp = client.open_sftp()

                def callback(transferred: int, total: int):
                    self.uploadProgress.emit(filename, transferred, total)

                sftp.put(str(local_file), remote_path, callback=callback)
                self.uploadCompleted.emit(remote_path, True, f"Uploaded {filename} successfully")
                self.statusChanged.emit(f"Uploaded {filename} to {remote_path}")

                # Refresh the current directory if it's the parent
                parent_dir = posixpath.dirname(remote_path)
                if self._current_path == parent_dir:
                    try:
                        entries = self._list_entries(client, self._current_path)
                        self._publish_entries(self._current_path, entries)
                    except Exception:
                        pass

            except Exception as exc:
                self.uploadCompleted.emit(remote_path, False, str(exc))
                self.statusChanged.emit(f"Upload failed: {exc}")
            finally:
                if sftp:
                    try:
                        sftp.close()
                    except Exception:
                        pass
                client.close()

        self._start_worker(operation)

    @Slot(str, str)
    def downloadFile(self, remote_path: str, local_path: str) -> None:
        """Download a file from the server via SFTP."""
        if self._settings is None:
            self.errorOccurred.emit("Connect to the server first.")
            return
        if not local_path or not remote_path:
            self.errorOccurred.emit("Both local and remote paths are required.")
            return
        if not remote_path.startswith("/"):
            self.errorOccurred.emit("Remote path must be absolute (starting with /).")
            return
        remote_path = _normalize_remote_path(remote_path)
        settings = self._settings.copy()

        def operation() -> None:
            local_file = Path(local_path)
            # Ensure parent directory exists
            local_file.parent.mkdir(parents=True, exist_ok=True)

            # Reset cancellation flag for this download
            self._download_cancelled.clear()

            self.statusChanged.emit(f"Downloading {remote_path}…")
            self.downloadProgress.emit(posixpath.basename(remote_path), 0, 0)

            client = self._open_client(settings)
            sftp = None
            try:
                sftp = client.open_sftp()

                # Get file size first
                stat = sftp.stat(remote_path)
                file_size = stat.st_size
                filename = posixpath.basename(remote_path)

                def callback(transferred: int, total: int):
                    if self._download_cancelled.is_set():
                        raise RuntimeError("Download cancelled")
                    self.downloadProgress.emit(filename, transferred, total)

                sftp.get(remote_path, str(local_file), callback=callback)
                self.downloadCompleted.emit(local_path, True, f"Downloaded {filename} successfully")
                self.statusChanged.emit(f"Downloaded {filename} to {local_path}")

            except Exception as exc:
                self.downloadCompleted.emit(local_path, False, str(exc))
                self.statusChanged.emit(f"Download failed: {exc}")
            finally:
                if sftp:
                    try:
                        sftp.close()
                    except Exception:
                        pass
                client.close()

        self._start_worker(operation)

    @Slot()
    def cancelDownload(self) -> None:
        """Request cancellation of the in-progress SFTP download.

        The download callback checks this flag and aborts the transfer by
        raising an exception, which surfaces through ``downloadCompleted``.
        """
        self._download_cancelled.set()

    @staticmethod
    def _list_disk_usage(client: paramiko.SSHClient) -> list[dict[str, Any]]:
        command = "python3 -c " + shlex.quote(_DISK_USAGE_SCRIPT)
        output = Backend._run_remote(client, command)
        try:
            rows = json.loads(output) if output.strip() else []
        except json.JSONDecodeError as exc:
            raise RuntimeError("The server returned an invalid disk usage report.") from exc
        if not isinstance(rows, list):
            raise RuntimeError("The server returned an invalid disk usage report.")
        return rows

    @staticmethod
    def _list_block_devices(client: paramiko.SSHClient) -> list[dict[str, Any]]:
        command = "python3 -c " + shlex.quote(_LIST_BLOCK_DEVICES_SCRIPT)
        output = Backend._run_remote(client, command)
        try:
            rows = json.loads(output) if output.strip() else []
        except json.JSONDecodeError as exc:
            raise RuntimeError("The server returned an invalid device list.") from exc
        if not isinstance(rows, list):
            raise RuntimeError("The server returned an invalid device list.")
        return rows

    @staticmethod
    def _directory_stats(client: paramiko.SSHClient, remote_path: str) -> dict[str, Any]:
        command = (
            "python3 -c "
            + shlex.quote(_DIRECTORY_STATS_SCRIPT)
            + " "
            + shlex.quote(remote_path)
        )
        output = Backend._run_remote(client, command)
        try:
            stats = json.loads(output) if output.strip() else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError("The server returned invalid directory statistics.") from exc
        if not isinstance(stats, dict):
            raise RuntimeError("The server returned invalid directory statistics.")
        return stats

    @staticmethod
    def _validate_entry_name(name: str, label: str = "name") -> str | None:
        if not name:
            return f"Enter a value for the {label}."
        if "/" in name or "\x00" in name:
            return f"The {label} cannot contain '/'."
        if name in (".", ".."):
            return f"'{name}' is not a valid {label}."
        return None

    @staticmethod
    def _archive_item(name: str) -> str:
        # A leading dash would be parsed as a command option.
        return "./" + name if name.startswith("-") else name

    @classmethod
    def _archive_create_command(
        cls,
        parent: str,
        archive_name: str,
        names: list[str],
        format_name: str,
        tool: str,
    ) -> str:
        spec = ARCHIVE_FORMATS[format_name]
        archive = shlex.quote(cls._archive_item(archive_name))
        items = " ".join(shlex.quote(cls._archive_item(name)) for name in names)
        return (
            "cd "
            + shlex.quote(parent)
            + " && "
            + str(spec["create"]).format(tool=tool, archive=archive, items=items)
        )

    @classmethod
    def _archive_extract_command(
        cls, archive_path: str, destination: str, format_name: str, tool: str
    ) -> str:
        spec = ARCHIVE_FORMATS[format_name]
        target = destination.rstrip("/") + "/" if format_name == "rar" else destination
        return str(spec["extract"]).format(
            tool=tool,
            archive=shlex.quote(archive_path),
            dest=shlex.quote(target),
        )

    @staticmethod
    def _transfer_command(sources: list[str], destination: str, move: bool) -> str:
        program = "mv" if move else "cp -a"
        items = " ".join(shlex.quote(source) for source in sources)
        target = destination.rstrip("/") + "/"
        return f"{program} -- {items} {shlex.quote(target)}"

    @classmethod
    def _require_tool(cls, client: paramiko.SSHClient, alternatives: tuple[str, ...]) -> str:
        script = (
            "import json, shutil, sys\n"
            "print(json.dumps({tool: bool(shutil.which(tool)) for tool in sys.argv[1:]}))"
        )
        command = (
            "python3 -c "
            + shlex.quote(script)
            + " "
            + " ".join(shlex.quote(tool) for tool in alternatives)
        )
        found = json.loads(cls._run_remote(client, command))
        for tool in alternatives:
            if found.get(tool):
                return tool
        raise RuntimeError(
            "The server does not have "
            + " or ".join(alternatives)
            + " installed."
        )

    def _start_worker(self, operation: Callable[[], None], busy: bool = True) -> None:
        if busy and self._busy:
            self.errorOccurred.emit("Please wait for the current operation to finish.")
            return
        if busy:
            self._busy = True
            self.busyChanged.emit(True)

        def run() -> None:
            try:
                operation()
            except Exception as exc:
                try:
                    self.errorOccurred.emit(str(exc))
                    self.statusChanged.emit("Operation failed.")
                except RuntimeError:
                    pass  # backend was deleted; nothing can be delivered
            finally:
                if busy:
                    self._busy = False
                    try:
                        self.busyChanged.emit(False)
                    except RuntimeError:
                        pass
                self._workers.discard(threading.current_thread())

        worker = threading.Thread(target=run, daemon=True)
        self._workers.add(worker)
        worker.start()

    @staticmethod
    def _known_hosts_path() -> Path:
        return Path.home() / ".deepzoom-cleaner" / "known_hosts"

    @classmethod
    def _store_host_key(cls, hostname: str, key: paramiko.PKey) -> None:
        path = cls._known_hosts_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        host_keys = paramiko.HostKeys()
        if path.exists():
            host_keys.load(str(path))
        host_keys.add(hostname, key.get_name(), key)
        host_keys.save(str(path))

    @staticmethod
    def _fingerprint(key: paramiko.PKey) -> str:
        digest = hashlib.sha256(key.asbytes()).digest()
        return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")

    @classmethod
    def _open_client(cls, settings: dict[str, Any]) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        known_hosts = cls._known_hosts_path()
        if known_hosts.exists():
            client.load_host_keys(str(known_hosts))
        client.set_missing_host_key_policy(_ConfirmMissingHostKey())
        try:
            client.connect(
                hostname=settings["host"],
                port=settings["port"],
                username=settings["username"],
                password=settings["password"],
                key_filename=settings["key_filename"],
                timeout=20,
                banner_timeout=20,
                auth_timeout=20,
                allow_agent=True,
                look_for_keys=True,
            )
        except Exception:
            client.close()
            raise
        return client

    @staticmethod
    def _run_remote(client: paramiko.SSHClient, command: str) -> str:
        _, stdout, stderr = client.exec_command(command, get_pty=False)
        output = stdout.read().decode("utf-8", errors="strict")
        error_output = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            detail = error_output or f"Remote command exited with status {exit_code}."
            raise RuntimeError(detail)
        return output

    @classmethod
    def _list_folders(
        cls, client: paramiko.SSHClient, remote_path: str
    ) -> list[dict[str, str]]:
        command = (
            "python3 -c "
            + shlex.quote(_LIST_DIRECTORIES_SCRIPT)
            + " "
            + shlex.quote(remote_path)
        )
        try:
            output = cls._run_remote(client, command)
            folders = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeError("The server returned an invalid folder listing.") from exc
        if not isinstance(folders, list) or any(
            not isinstance(folder, dict)
            or not isinstance(folder.get("name"), str)
            or not isinstance(folder.get("path"), str)
            for folder in folders
        ):
            raise RuntimeError("The server returned an invalid folder listing.")
        return sorted(folders, key=lambda folder: folder["name"].casefold())

    @classmethod
    def _list_entries(
        cls, client: paramiko.SSHClient, remote_path: str
    ) -> list[dict[str, Any]]:
        command = (
            "python3 -c "
            + shlex.quote(_LIST_FILES_SCRIPT)
            + " "
            + shlex.quote(remote_path)
        )
        try:
            entries = json.loads(cls._run_remote(client, command))
        except json.JSONDecodeError as exc:
            raise RuntimeError("The server returned an invalid folder listing.") from exc
        if not isinstance(entries, list):
            raise RuntimeError("The server returned an invalid folder listing.")
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("name"), str)
                or not isinstance(entry.get("path"), str)
                or not isinstance(entry.get("is_dir"), bool)
            ):
                raise RuntimeError("The server returned an invalid folder listing.")
        return sorted(
            entries,
            key=lambda entry: (
                not entry["is_dir"],
                entry["name"].casefold(),
                entry["name"],
            ),
        )

    @classmethod
    def _remove_one(cls, client: paramiko.SSHClient, path: str) -> None:
        command = "rm -rf -- " + shlex.quote(path)
        cls._run_remote(client, command)
