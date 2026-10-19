import base64
import hashlib
import json
import shlex
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import paramiko
from PySide6.QtCore import QObject, QTimer, Signal, Slot


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
    errorOccurred = Signal(str)
    foldersLoaded = Signal(list)
    foldersRemoved = Signal(list)
    hostKeyTrustRequested = Signal(str, int, str)
    statusChanged = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._busy = False
        self._settings: dict[str, Any] | None = None
        self._listed_paths: set[str] = set()
        self._workers: set[threading.Thread] = set()
        self._pending_host_key: tuple[dict[str, Any], HostKeyConfirmationRequired] | None = None

    @Slot(str, str, str, str, str, str)
    def connectAndLoad(
        self,
        host: str,
        username: str,
        port_text: str,
        remote_path: str,
        key_filename: str,
        password: str,
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
                self.statusChanged.emit(
                    "Server identity needs verification before connecting."
                )
                return
            except paramiko.BadHostKeyException as exc:
                fingerprint = self._fingerprint(exc.key)
                self.errorOccurred.emit(
                    "The server's SSH host key has changed from the trusted key. "
                    f"Connection refused. Reported fingerprint: {fingerprint}"
                )
                self.statusChanged.emit("Server identity check failed.")
                return
            try:
                folders = self._list_folders(client, remote_path)
            finally:
                client.close()
            self._settings = settings
            self._listed_paths = {folder["path"] for folder in folders}
            self.foldersLoaded.emit(folders)
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
            finally:
                client.close()

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

    def _start_worker(self, operation: Callable[[], None]) -> None:
        if self._busy:
            self.errorOccurred.emit("Please wait for the current operation to finish.")
            return
        self._busy = True
        self.busyChanged.emit(True)

        def run() -> None:
            try:
                operation()
            except Exception as exc:
                self.errorOccurred.emit(str(exc))
                self.statusChanged.emit("Operation failed.")
            finally:
                self._busy = False
                self.busyChanged.emit(False)
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
    def _remove_one(cls, client: paramiko.SSHClient, path: str) -> None:
        command = "rm -rf -- " + shlex.quote(path)
        cls._run_remote(client, command)
