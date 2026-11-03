import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import paramiko
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy
import time

from deepzoom_cleaner.backend import (
    Backend,
    HostKeyConfirmationRequired,
    _LIST_DIRECTORIES_SCRIPT,
)


class FakeChannel:
    def recv_exit_status(self) -> int:
        return 0


class FakeStream:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.channel = FakeChannel()

    def read(self) -> bytes:
        return self.data


class FakeClient:
    def __init__(self, stdout: bytes = b"") -> None:
        self.command = ""
        self.stdout = stdout

    def exec_command(self, command: str, get_pty: bool = False):
        self.command = command
        return None, FakeStream(self.stdout), FakeStream(b"")


class FakeSSHClient:
    def __init__(self, key: paramiko.PKey) -> None:
        self.key = key
        self.policy = None
        self.closed = False

    def load_system_host_keys(self) -> None:
        pass

    def set_missing_host_key_policy(self, policy) -> None:
        self.policy = policy

    def connect(self, hostname: str, port: int, **kwargs) -> None:
        server_name = hostname if port == 22 else f"[{hostname}]:{port}"
        self.policy.missing_host_key(self, server_name, self.key)

    def close(self) -> None:
        self.closed = True


class BackendTests(unittest.TestCase):
    def test_listing_script_includes_unicode_directories_only(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            unicode_name = "تصاویر DeepZoom"
            os.mkdir(os.path.join(parent, unicode_name))
            with open(os.path.join(parent, "not-a-folder"), "w", encoding="utf-8"):
                pass

            result = subprocess.run(
                [sys.executable, "-c", _LIST_DIRECTORIES_SCRIPT, parent],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(
            json.loads(result.stdout),
            [{"name": unicode_name, "path": os.path.join(parent, unicode_name)}],
        )

    def test_remote_listing_preserves_unicode_names_and_quotes_path(self) -> None:
        parent = "/srv/deep zoom; echo unsafe"
        records = [
            {"name": "عکس فارسی", "path": parent + "/عکس فارسی"},
            {"name": "tiles", "path": parent + "/tiles"},
        ]
        client = FakeClient(json.dumps(records).encode("utf-8"))

        folders = Backend._list_folders(client, parent)

        self.assertEqual([folder["name"] for folder in folders], ["tiles", "عکس فارسی"])
        self.assertIn(shlex.quote(parent), client.command)
        self.assertIn("follow_symlinks=False", _LIST_DIRECTORIES_SCRIPT)

    def test_removal_quotes_remote_path(self) -> None:
        path = "/srv/tiles/سلام'; touch /tmp/unwanted"
        client = FakeClient()

        Backend._remove_one(client, path)

        self.assertEqual(client.command, "rm -rf -- " + shlex.quote(path))

    def test_unknown_host_key_requires_explicit_trust(self) -> None:
        key = paramiko.ECDSAKey.generate()
        client = FakeSSHClient(key)
        settings = {
            "host": "example.test",
            "port": 2222,
            "username": "user",
            "password": None,
            "key_filename": None,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            known_hosts = Path(temp_dir) / "known_hosts"
            with (
                patch("deepzoom_cleaner.backend.paramiko.SSHClient", return_value=client),
                patch.object(Backend, "_known_hosts_path", return_value=known_hosts),
            ):
                with self.assertRaises(HostKeyConfirmationRequired) as raised:
                    Backend._open_client(settings)

                self.assertEqual(raised.exception.hostname, "[example.test]:2222")
                self.assertTrue(client.closed)
                self.assertFalse(known_hosts.exists())

    def test_trusted_host_key_is_persisted_for_reconnect(self) -> None:
        key = paramiko.ECDSAKey.generate()
        with tempfile.TemporaryDirectory() as temp_dir:
            known_hosts = Path(temp_dir) / "app" / "known_hosts"
            with patch.object(Backend, "_known_hosts_path", return_value=known_hosts):
                Backend._store_host_key("[example.test]:2222", key)
                stored = paramiko.HostKeys(str(known_hosts))

        self.assertEqual(
            stored.lookup("[example.test]:2222").get(key.get_name()),
            key,
        )
        self.assertTrue(Backend._fingerprint(key).startswith("SHA256:"))

    def test_accepted_key_reconnects_using_saved_server_settings(self) -> None:
        key = paramiko.ECDSAKey.generate()
        settings = {
            "host": "example.test",
            "port": 2222,
            "username": "user",
            "remote_path": "/srv/deepzoom",
            "key_filename": None,
            "password": "secret",
        }
        backend = Backend()
        backend._pending_host_key = (
            settings,
            HostKeyConfirmationRequired("[example.test]:2222", key),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            known_hosts = Path(temp_dir) / "known_hosts"
            with (
                patch.object(Backend, "_known_hosts_path", return_value=known_hosts),
                patch.object(backend, "connectAndLoad") as reconnect,
            ):
                backend.acceptPendingHostKey()

        reconnect.assert_called_once_with(
            "example.test", "user", "2222", "/srv/deepzoom", "", "secret"
        )
        self.assertIsNone(backend._pending_host_key)


class UploadDownloadTests(unittest.TestCase):
    """Tests for uploadFile and downloadFile covering every failure case."""

    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication([])

    def setUp(self):
        self.backend = Backend()

    # -- helpers -----------------------------------------------------------

    def _wait_for_busy(self, timeout: float = 10.0) -> None:
        """Wait for backend worker threads to complete, processing events."""
        start = time.time()
        while self.backend._busy and (time.time() - start) < timeout:
            self.app.processEvents()
            time.sleep(0.01)

    def _make_settings(self) -> dict:
        return {
            "host": "example.test",
            "port": 22,
            "username": "user",
            "remote_path": "/srv/deepzoom",
            "key_filename": None,
            "password": None,
        }

    # -- Upload validation (synchronous, no thread) -----------------------

    def test_upload_not_connected(self):
        spy = QSignalSpy(self.backend.errorOccurred)
        self.backend.uploadFile("/local/file.txt", "/remote/file.txt")
        self.assertEqual(spy.size(), 1)
        self.assertIn("Connect to the server first", spy.at(0)[0])

    def test_upload_empty_local_path(self):
        self.backend._settings = self._make_settings()
        spy = QSignalSpy(self.backend.errorOccurred)
        self.backend.uploadFile("", "/remote/file.txt")
        self.assertEqual(spy.size(), 1)
        self.assertIn("Both local and remote paths are required", spy.at(0)[0])

    def test_upload_empty_remote_path(self):
        self.backend._settings = self._make_settings()
        spy = QSignalSpy(self.backend.errorOccurred)
        self.backend.uploadFile("/local/file.txt", "")
        self.assertEqual(spy.size(), 1)
        self.assertIn("Both local and remote paths are required", spy.at(0)[0])

    def test_upload_remote_path_not_absolute(self):
        self.backend._settings = self._make_settings()
        spy = QSignalSpy(self.backend.errorOccurred)
        self.backend.uploadFile("/local/file.txt", "relative/path.txt")
        self.assertEqual(spy.size(), 1)
        self.assertIn("Remote path must be absolute", spy.at(0)[0])

    # -- Upload local file checks (async worker thread) -------------------

    def test_upload_local_file_not_found(self):
        self.backend._settings = self._make_settings()
        spy = QSignalSpy(self.backend.uploadCompleted)
        self.backend.uploadFile("/nonexistent/file.txt", "/remote/file.txt")
        self._wait_for_busy()
        self.assertEqual(spy.size(), 1)
        self.assertFalse(spy.at(0)[1])
        self.assertIn("Local file not found", spy.at(0)[2])

    def test_upload_local_path_is_directory(self):
        self.backend._settings = self._make_settings()
        spy = QSignalSpy(self.backend.uploadCompleted)
        with tempfile.TemporaryDirectory() as tmpdir:
            self.backend.uploadFile(tmpdir, "/remote/file.txt")
            self._wait_for_busy()
        self.assertEqual(spy.size(), 1)
        self.assertFalse(spy.at(0)[1])
        self.assertIn("Local file not found", spy.at(0)[2])

    # -- Upload SFTP failure (async worker thread) ------------------------

    def test_upload_sftp_put_permission_denied(self):
        self.backend._settings = self._make_settings()
        with patch.object(self.backend, "_open_client") as mock_open:
            mock_client = MagicMock()
            mock_sftp = MagicMock()
            mock_client.open_sftp.return_value = mock_sftp
            mock_open.return_value = mock_client
            mock_sftp.put.side_effect = PermissionError("Permission denied")

            import os
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
                f.write(b"test content")
                temp_path = f.name

            try:
                spy = QSignalSpy(self.backend.uploadCompleted)
                self.backend.uploadFile(temp_path, "/remote/file.txt")
                self._wait_for_busy()
                self.assertEqual(spy.size(), 1)
                self.assertFalse(spy.at(0)[1])
                self.assertIn("Permission denied", spy.at(0)[2])
                mock_sftp.put.assert_called_once()
            finally:
                os.unlink(temp_path)

    def test_upload_sftp_connection_lost(self):
        self.backend._settings = self._make_settings()
        with patch.object(self.backend, "_open_client") as mock_open:
            mock_client = MagicMock()
            mock_sftp = MagicMock()
            mock_client.open_sftp.return_value = mock_sftp
            mock_open.return_value = mock_client
            mock_sftp.put.side_effect = OSError("Lost connection")

            import os
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
                f.write(b"test content")
                temp_path = f.name

            try:
                spy = QSignalSpy(self.backend.uploadCompleted)
                self.backend.uploadFile(temp_path, "/remote/file.txt")
                self._wait_for_busy()
                self.assertEqual(spy.size(), 1)
                self.assertFalse(spy.at(0)[1])
                self.assertIn("Lost connection", spy.at(0)[2])
            finally:
                os.unlink(temp_path)

    # -- Upload success -----------------------------------------------------

    def test_upload_success(self):
        self.backend._settings = self._make_settings()
        with patch.object(self.backend, "_open_client") as mock_open:
            mock_client = MagicMock()
            mock_sftp = MagicMock()
            mock_client.open_sftp.return_value = mock_sftp
            mock_open.return_value = mock_client

            import os
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
                f.write(b"test content")
                temp_path = f.name

            try:
                spy = QSignalSpy(self.backend.uploadCompleted)
                self.backend.uploadFile(temp_path, "/remote/file.txt")
                self._wait_for_busy()
                self.assertEqual(spy.size(), 1)
                self.assertTrue(spy.at(0)[1])
                self.assertIn("Uploaded", spy.at(0)[2])
                mock_sftp.put.assert_called_once()
            finally:
                os.unlink(temp_path)

    # -- Download validation (synchronous, no thread) ----------------------

    def test_download_not_connected(self):
        spy = QSignalSpy(self.backend.errorOccurred)
        self.backend.downloadFile("/remote/file.txt", "/local/file.txt")
        self.assertEqual(spy.size(), 1)
        self.assertIn("Connect to the server first", spy.at(0)[0])

    def test_download_empty_local_path(self):
        self.backend._settings = self._make_settings()
        spy = QSignalSpy(self.backend.errorOccurred)
        self.backend.downloadFile("/remote/file.txt", "")
        self.assertEqual(spy.size(), 1)
        self.assertIn("Both local and remote paths are required", spy.at(0)[0])

    def test_download_empty_remote_path(self):
        self.backend._settings = self._make_settings()
        spy = QSignalSpy(self.backend.errorOccurred)
        self.backend.downloadFile("", "/local/file.txt")
        self.assertEqual(spy.size(), 1)
        self.assertIn("Both local and remote paths are required", spy.at(0)[0])

    def test_download_remote_path_not_absolute(self):
        self.backend._settings = self._make_settings()
        spy = QSignalSpy(self.backend.errorOccurred)
        self.backend.downloadFile("relative/path.txt", "/local/file.txt")
        self.assertEqual(spy.size(), 1)
        self.assertIn("Remote path must be absolute", spy.at(0)[0])

    # -- Download remote file checks (async worker thread) -----------------

    def test_download_remote_file_not_found(self):
        self.backend._settings = self._make_settings()
        with patch.object(self.backend, "_open_client") as mock_open:
            mock_client = MagicMock()
            mock_sftp = MagicMock()
            mock_client.open_sftp.return_value = mock_sftp
            mock_open.return_value = mock_client
            mock_sftp.stat.side_effect = FileNotFoundError("No such file")

            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = str(Path(tmpdir) / "downloaded.txt")
                spy = QSignalSpy(self.backend.downloadCompleted)
                self.backend.downloadFile("/remote/nonexistent.txt", local_path)
                self._wait_for_busy()
                self.assertEqual(spy.size(), 1)
                self.assertFalse(spy.at(0)[1])
                self.assertIn("No such file", spy.at(0)[2])

    # -- Download SFTP failure (async worker thread) ----------------------

    def test_download_sftp_get_failure(self):
        self.backend._settings = self._make_settings()
        with patch.object(self.backend, "_open_client") as mock_open:
            mock_client = MagicMock()
            mock_sftp = MagicMock()
            mock_client.open_sftp.return_value = mock_sftp
            mock_open.return_value = mock_client

            mock_stat = MagicMock()
            mock_stat.st_size = 100
            mock_sftp.stat.return_value = mock_stat
            mock_sftp.get.side_effect = IOError("Disk full")

            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = str(Path(tmpdir) / "downloaded.txt")
                spy = QSignalSpy(self.backend.downloadCompleted)
                self.backend.downloadFile("/remote/file.txt", local_path)
                self._wait_for_busy()
                self.assertEqual(spy.size(), 1)
                self.assertFalse(spy.at(0)[1])
                self.assertIn("Disk full", spy.at(0)[2])

    def test_download_sftp_connection_lost(self):
        self.backend._settings = self._make_settings()
        with patch.object(self.backend, "_open_client") as mock_open:
            mock_client = MagicMock()
            mock_sftp = MagicMock()
            mock_client.open_sftp.return_value = mock_sftp
            mock_open.return_value = mock_client

            mock_stat = MagicMock()
            mock_stat.st_size = 100
            mock_sftp.stat.return_value = mock_stat
            mock_sftp.get.side_effect = OSError("Lost connection")

            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = str(Path(tmpdir) / "downloaded.txt")
                spy = QSignalSpy(self.backend.downloadCompleted)
                self.backend.downloadFile("/remote/file.txt", local_path)
                self._wait_for_busy()
                self.assertEqual(spy.size(), 1)
                self.assertFalse(spy.at(0)[1])
                self.assertIn("Lost connection", spy.at(0)[2])

    # -- Download success -----------------------------------------------------

    def test_download_success(self):
        self.backend._settings = self._make_settings()
        with patch.object(self.backend, "_open_client") as mock_open:
            mock_client = MagicMock()
            mock_sftp = MagicMock()
            mock_client.open_sftp.return_value = mock_sftp
            mock_open.return_value = mock_client

            mock_stat = MagicMock()
            mock_stat.st_size = 100
            mock_sftp.stat.return_value = mock_stat

            with tempfile.TemporaryDirectory() as tmpdir:
                local_path = str(Path(tmpdir) / "downloaded.txt")
                spy = QSignalSpy(self.backend.downloadCompleted)
                self.backend.downloadFile("/remote/file.txt", local_path)
                self._wait_for_busy()
                self.assertEqual(spy.size(), 1)
                self.assertTrue(spy.at(0)[1])
                self.assertIn("Downloaded", spy.at(0)[2])
                mock_sftp.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
