import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QMessageBox

import build
from build_gui import BuildWindow


class BuildWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = BuildWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_window_exposes_current_platform_choices(self) -> None:
        self.assertEqual(
            set(self.window._format_checks),
            set(build.PLATFORM_FORMATS[build.current_platform()]),
        )
        self.assertEqual(self.window.selected_formats(), ())
        self.assertFalse(self.window.build_button.isEnabled())

    def test_all_format_button_and_method_selection_match_cli_options(self) -> None:
        self.window._set_all_formats(True)
        self.window.method_combo.setCurrentText("Both")

        self.assertEqual(
            self.window.selected_formats(),
            build.PLATFORM_FORMATS[build.current_platform()],
        )
        self.assertEqual(self.window.selected_method(), "both")
        self.assertEqual(self.window._methods_for_selection(), build.METHODS)
        self.assertTrue(self.window.build_button.isEnabled())

        self.window._set_all_formats(False)
        self.assertEqual(self.window.selected_formats(), ())
        self.assertFalse(self.window.build_button.isEnabled())

    def test_build_arguments_include_multiple_formats_and_output_directory(self) -> None:
        platform_formats = build.PLATFORM_FORMATS[self.window.target]
        self.window._format_checks[platform_formats[0]].setChecked(True)
        self.window._format_checks[platform_formats[-1]].setChecked(True)
        self.window.method_combo.setCurrentText("Nuitka")
        self.window.output_edit.setText("release output")

        arguments = self.window.build_arguments()

        self.assertEqual(arguments[0], str(build.ROOT / "build.py"))
        self.assertEqual(arguments[arguments.index("--method") + 1], "nuitka")
        self.assertEqual(arguments[arguments.index("--output") + 1], "release output")
        self.assertEqual(
            [arguments[index + 1] for index, arg in enumerate(arguments) if arg == "--format"],
            [platform_formats[0], platform_formats[-1]],
        )

    def test_build_arguments_require_a_selected_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            self.window.build_arguments()

    def test_start_build_runs_cli_with_selected_options(self) -> None:
        format_name = build.PLATFORM_FORMATS[self.window.target][0]
        self.window._format_checks[format_name].setChecked(True)
        self.window.method_combo.setCurrentText("Nuitka")

        with (
            patch("build_gui.build.missing_external_tools", return_value=[]),
            patch("build_gui.build.missing_python_build_packages", return_value=[]),
            patch(
                "build_gui.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch.object(self.window, "_launch_process") as launch,
        ):
            self.window._start_build()

        args, kwargs = launch.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertEqual(args[0][1], str(build.ROOT / "build.py"))
        self.assertEqual(kwargs["phase"], "build")
        self.assertIn(format_name, args[0])

    def test_missing_build_dependencies_are_only_installed_after_confirmation(self) -> None:
        format_name = build.PLATFORM_FORMATS[self.window.target][0]
        self.window._format_checks[format_name].setChecked(True)

        with (
            patch("build_gui.build.missing_external_tools", return_value=[]),
            patch(
                "build_gui.build.missing_python_build_packages",
                return_value=["PyInstaller"],
            ),
            patch(
                "build_gui.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ),
            patch.object(self.window, "_launch_process") as launch,
        ):
            self.window._start_build()

        args, kwargs = launch.call_args
        self.assertEqual(args[0][:3], [sys.executable, "-m", "pip"])
        self.assertIn("requirements-build.txt", args[0][-1])
        self.assertEqual(kwargs["phase"], "install")

    def test_missing_native_tools_prevent_build(self) -> None:
        format_name = build.PLATFORM_FORMATS[self.window.target][0]
        self.window._format_checks[format_name].setChecked(True)

        with (
            patch(
                "build_gui.build.missing_external_tools",
                return_value=[("missing-tool",)],
            ),
            patch("build_gui.QMessageBox.warning") as warning,
            patch.object(self.window, "_launch_process") as launch,
        ):
            self.window._start_build()

        warning.assert_called_once()
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
