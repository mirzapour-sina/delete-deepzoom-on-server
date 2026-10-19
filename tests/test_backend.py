import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paramiko

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


if __name__ == "__main__":
    unittest.main()
