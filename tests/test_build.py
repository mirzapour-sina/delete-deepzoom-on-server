import tempfile
import unittest
import zipfile
from pathlib import Path
from importlib.machinery import ModuleSpec
from unittest.mock import Mock, patch
from xml.etree import ElementTree

import build


class InputAnswers:
    def __init__(self, answers: tuple[str, ...]) -> None:
        self.answers = iter(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return next(self.answers)


class BuildConfigurationTests(unittest.TestCase):
    def test_platform_names_are_normalized(self) -> None:
        self.assertEqual(build.current_platform("Windows"), "windows")
        self.assertEqual(build.current_platform("Linux"), "linux")
        self.assertEqual(build.current_platform("Darwin"), "macos")
        with self.assertRaisesRegex(RuntimeError, "Unsupported build platform"):
            build.current_platform("FreeBSD")

    def test_architecture_names_are_normalized(self) -> None:
        self.assertEqual(build.normalized_architecture("AMD64"), "x86_64")
        self.assertEqual(build.normalized_architecture("arm64"), "aarch64")

    def test_interactive_configuration_accepts_all_choices(self) -> None:
        answers = InputAnswers(("3", "0", "", "1"))
        output: list[str] = []

        config = build.interactive_configuration(
            target="windows",
            input_fn=answers,
            print_fn=output.append,
        )

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.method, "both")
        self.assertEqual(config.methods, build.METHODS)
        self.assertEqual(config.formats, build.PLATFORM_FORMATS["windows"])
        self.assertEqual(config.output, build.ROOT / "dist-packages")
        self.assertTrue(config.interactive)
        self.assertTrue(any("Windows installer (.exe)" in line for line in output))

    def test_interactive_configuration_retries_bad_format_selection(self) -> None:
        answers = InputAnswers(("1", "invalid", "1,3", "artifacts", "1"))

        config = build.interactive_configuration(
            target="windows",
            input_fn=answers,
            print_fn=Mock(),
        )

        self.assertIsNotNone(config)
        assert config is not None
        self.assertEqual(config.method, "pyinstaller")
        self.assertEqual(config.formats, ("portable", "msi"))
        self.assertEqual(config.output, Path("artifacts"))

    def test_interactive_configuration_can_be_cancelled(self) -> None:
        config = build.interactive_configuration(
            target="linux",
            input_fn=InputAnswers(("q",)),
            print_fn=Mock(),
        )

        self.assertIsNone(config)

    def test_gui_flag_opens_graphical_builder(self) -> None:
        with patch("build_gui.main", return_value=7) as gui_main:
            result = build.main(["--gui"])

        self.assertEqual(result, 7)
        gui_main.assert_called_once()

    def test_all_and_selected_formats_are_platform_specific(self) -> None:
        self.assertEqual(
            build.selected_formats("windows", ["all"]),
            ("portable", "inno", "msi"),
        )
        self.assertEqual(
            build.selected_formats("macos", ["pkg", "dmg", "pkg"]),
            ("pkg", "dmg"),
        )
        with self.assertRaisesRegex(ValueError, "not available for linux"):
            build.selected_formats("linux", ["inno"])
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            build.selected_formats("windows", ["all", "msi"])

    def test_external_tool_preflight_lists_missing_tools(self) -> None:
        def available(name: str) -> str | None:
            return "tool" if name == "dpkg-deb" else None

        missing = build.missing_external_tools(
            "linux",
            ("pyinstaller", "nuitka"),
            ("deb", "appimage"),
            which=available,
        )

        self.assertEqual(
            missing,
            [
                ("cc", "gcc", "clang"),
                (
                    "linuxdeploy",
                    f"linuxdeploy-{build.normalized_architecture()}.AppImage",
                ),
            ],
        )

    def test_noninteractive_missing_build_tools_explains_install_command(self) -> None:
        with (
            patch("build.importlib.util.find_spec", return_value=None),
            self.assertRaisesRegex(
                RuntimeError,
                "python -m pip install -r requirements-build.txt",
            ),
        ):
            build.ensure_python_build_packages(("pyinstaller",), interactive=False)

    def test_interactive_missing_python_package_can_be_installed(self) -> None:
        answers = InputAnswers(("yes",))
        with (
            patch(
                "build.importlib.util.find_spec",
                side_effect=(None, ModuleSpec("PyInstaller", loader=None)),
            ),
            patch("build.install_python_build_requirements") as install,
        ):
            build.ensure_python_build_packages(
                ("pyinstaller",),
                interactive=True,
                input_fn=answers,
                print_fn=Mock(),
            )

        install.assert_called_once_with()

    def test_interactive_missing_python_package_can_be_declined(self) -> None:
        with (
            patch("build.importlib.util.find_spec", return_value=None),
            patch("build.install_python_build_requirements") as install,
            self.assertRaisesRegex(RuntimeError, "Build cancelled"),
        ):
            build.ensure_python_build_packages(
                ("nuitka",),
                interactive=True,
                input_fn=InputAnswers(("n",)),
                print_fn=Mock(),
            )

        install.assert_not_called()

    def test_portable_archive_keeps_app_directory_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle" / "DeepZoomCleaner"
            bundle.mkdir(parents=True)
            (bundle / "DeepZoomCleaner.exe").write_bytes(b"executable")
            (bundle / "runtime.dll").write_bytes(b"dependency")
            archive_path = root / "artifacts" / "portable.zip"

            result = build.write_archive(bundle, archive_path)

            self.assertEqual(result, archive_path)
            with zipfile.ZipFile(result) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "DeepZoomCleaner/DeepZoomCleaner.exe",
                        "DeepZoomCleaner/runtime.dll",
                    },
                )

    def test_wix_source_contains_package_files_and_start_menu_shortcut(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            nested = bundle / "_internal"
            nested.mkdir(parents=True)
            (bundle / "DeepZoomCleaner.exe").write_bytes(b"application")
            (nested / "Qt6Core.dll").write_bytes(b"runtime")
            output = root / "msi"

            with (
                patch("build.find_tool", return_value="wix"),
                patch("build.run") as run_command,
            ):
                result = build.create_msi_installer(bundle, output)

            self.assertEqual(result, output / "DeepZoomCleaner.msi")
            source_path = output.parent / "DeepZoomCleaner.wxs"
            xml_root = ElementTree.parse(source_path).getroot()
            namespace = {"wix": build.WIX_NAMESPACE}
            self.assertEqual(len(xml_root.findall(".//wix:File", namespace)), 2)
            self.assertEqual(
                len(xml_root.findall(".//wix:Shortcut", namespace)),
                1,
            )
            self.assertIsNotNone(
                xml_root.find("wix:Fragment/wix:ComponentGroup", namespace)
            )
            run_command.assert_called_once()

    def test_inno_installer_script_points_to_standalone_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            bundle.mkdir()
            output = root / "inno"
            with (
                patch("build.find_tool", return_value="ISCC.exe"),
                patch("build.run") as run_command,
            ):
                result = build.create_inno_installer(bundle, output)

            self.assertEqual(result, output / "DeepZoomCleaner-Setup.exe")
            script = (root / "DeepZoomCleaner.iss").read_text(encoding="utf-8")
            self.assertIn("AppId={{A264EB5B-516E-4A4C-9348-9816B8780001}", script)
            self.assertIn(str(bundle.resolve()), script)
            run_command.assert_called_once()

    def test_builder_commands_include_qml_and_collect_the_app_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pyinstaller_output = root / "pyinstaller" / build.APP_NAME

            def fake_pyinstaller_run(command) -> None:
                destination = Path(command[command.index("--distpath") + 1])
                generated_bundle = destination / build.APP_NAME
                generated_bundle.mkdir(parents=True)
                (generated_bundle / "DeepZoomCleaner.exe").write_bytes(b"exe")

            with patch("build.run", side_effect=fake_pyinstaller_run) as run_command:
                bundle = build.build_pyinstaller(root, "windows")

            self.assertEqual(bundle, pyinstaller_output)
            pyinstaller_command = run_command.call_args.args[0]
            self.assertIn("PyInstaller", pyinstaller_command)
            self.assertIn("PySide6", pyinstaller_command)
            self.assertIn("paramiko", pyinstaller_command)
            self.assertIn("cryptography", pyinstaller_command)
            self.assertIn("qml", pyinstaller_command[pyinstaller_command.index("--add-data") + 1])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def fake_nuitka_run(command) -> None:
                output_arg = next(arg for arg in command if arg.startswith("--output-dir="))
                generated_dist = Path(output_arg.partition("=")[2]) / "main.dist"
                generated_dist.mkdir(parents=True)
                (generated_dist / "main.exe").write_bytes(b"exe")
                (generated_dist / "runtime.dll").write_bytes(b"dll")

            with patch("build.run", side_effect=fake_nuitka_run) as run_command:
                bundle = build.build_nuitka(root, "windows")

            self.assertEqual(bundle.name, "nuitka-bundle")
            self.assertTrue((bundle / "DeepZoomCleaner.exe").is_file())
            self.assertTrue((bundle / "runtime.dll").is_file())
            nuitka_command = run_command.call_args.args[0]
            self.assertIn("--mode=standalone", nuitka_command)
            self.assertIn("--enable-plugin=pyside6", nuitka_command)
            self.assertIn("--windows-console-mode=disable", nuitka_command)

    def test_macos_builders_preserve_native_app_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pyinstaller_app = root / "pyinstaller" / f"{build.APP_NAME}.app"

            def fake_pyinstaller_run(command) -> None:
                executable = (
                    Path(command[command.index("--distpath") + 1])
                    / f"{build.APP_NAME}.app"
                    / "Contents"
                    / "MacOS"
                    / build.APP_NAME
                )
                executable.parent.mkdir(parents=True)
                executable.write_bytes(b"app")

            with patch("build.run", side_effect=fake_pyinstaller_run) as run_command:
                bundle = build.build_pyinstaller(root, "macos")

            self.assertEqual(bundle, pyinstaller_app)
            self.assertIn("--windowed", run_command.call_args.args[0])

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nuitka_app = root / "nuitka" / f"{build.APP_NAME}.app"

            def fake_nuitka_run(command) -> None:
                output_arg = next(arg for arg in command if arg.startswith("--output-dir="))
                executable = (
                    Path(output_arg.partition("=")[2])
                    / f"{build.APP_NAME}.app"
                    / "Contents"
                    / "MacOS"
                    / build.APP_NAME
                )
                executable.parent.mkdir(parents=True)
                executable.write_bytes(b"app")

            with patch("build.run", side_effect=fake_nuitka_run) as run_command:
                bundle = build.build_nuitka(root, "macos")

            self.assertEqual(bundle, nuitka_app)
            self.assertIn("--macos-create-app-bundle", run_command.call_args.args[0])

    def test_generated_icon_has_a_valid_png_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            icon = Path(temporary) / "icon.png"
            build.create_icon(icon)
            self.assertEqual(icon.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
