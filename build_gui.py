from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QComboBox,
    QVBoxLayout,
    QWidget,
)

import build


FORMAT_LABELS = {
    "portable": "Portable ZIP archive",
    "inno": "Windows installer (.exe) - Inno Setup",
    "msi": "Windows Installer package (.msi) - WiX",
    "appimage": "Linux AppImage",
    "deb": "Debian / Ubuntu package (.deb)",
    "dmg": "macOS disk image (.dmg)",
    "pkg": "macOS installer package (.pkg)",
}
METHOD_LABELS = {
    "PyInstaller": "pyinstaller",
    "Nuitka": "nuitka",
    "Both": "both",
}


class BuildWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.target = build.current_platform()
        self._process: QProcess | None = None
        self._process_phase = ""
        self._format_checks: dict[str, QCheckBox] = {}
        self._create_ui()

    def _create_ui(self) -> None:
        self.setWindowTitle(f"{build.DISPLAY_NAME} - Builder")
        self.resize(860, 720)
        self.setMinimumSize(680, 560)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Standalone App Builder")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #1e293b;")
        layout.addWidget(title)

        target_box = QGroupBox("Build target")
        target_layout = QVBoxLayout(target_box)
        self.target_label = QLabel(
            f"{self.target.title()} - {build.normalized_architecture()}"
        )
        self.target_label.setStyleSheet("font-weight: 600;")
        target_layout.addWidget(self.target_label)
        target_layout.addWidget(
            QLabel(
                "Native packages are built for this computer's OS. "
                "Use a Windows, Linux, or macOS runner for other targets."
            )
        )
        layout.addWidget(target_box)

        options_box = QGroupBox("Build options")
        options_layout = QGridLayout(options_box)
        options_layout.addWidget(QLabel("Builder"), 0, 0)
        self.method_combo = QComboBox()
        self.method_combo.addItems(METHOD_LABELS)
        options_layout.addWidget(self.method_combo, 0, 1)
        layout.addWidget(options_box)

        formats_box = QGroupBox("Installer / archive formats")
        formats_layout = QVBoxLayout(formats_box)
        all_row = QHBoxLayout()
        all_row.addWidget(QLabel(f"Available for {self.target.title()}:"))
        all_row.addStretch(1)
        self.select_all_button = QPushButton("Select all")
        self.select_none_button = QPushButton("Select none")
        self.select_all_button.clicked.connect(lambda: self._set_all_formats(True))
        self.select_none_button.clicked.connect(lambda: self._set_all_formats(False))
        all_row.addWidget(self.select_all_button)
        all_row.addWidget(self.select_none_button)
        formats_layout.addLayout(all_row)
        for format_name in build.PLATFORM_FORMATS[self.target]:
            checkbox = QCheckBox(FORMAT_LABELS[format_name])
            checkbox.setProperty("formatName", format_name)
            checkbox.toggled.connect(self._sync_controls)
            self._format_checks[format_name] = checkbox
            formats_layout.addWidget(checkbox)
        layout.addWidget(formats_box)

        output_box = QGroupBox("Output folder")
        output_layout = QHBoxLayout(output_box)
        self.output_edit = QLineEdit(str(build.ROOT / "dist-packages"))
        self.output_edit.setPlaceholderText("Choose where to save installers")
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self._browse_output)
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(self.browse_button)
        layout.addWidget(output_box)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText(
            "Build output and errors will appear here."
        )
        self.log_output.setMaximumBlockCount(3000)
        layout.addWidget(self.log_output, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("Ready.")
        self.status_label.setWordWrap(True)
        bottom.addWidget(self.status_label, 1)
        self.cancel_button = QPushButton("Cancel build")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel_build)
        self.build_button = QPushButton("Build")
        self.build_button.setDefault(True)
        self.build_button.clicked.connect(self._start_build)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.build_button)
        layout.addLayout(bottom)

        self.setCentralWidget(central)
        self.setStyleSheet(
            "QMainWindow { background: #f4f6fa; }"
            "QGroupBox { font-weight: 600; border: 1px solid #cbd5e1;"
            "border-radius: 6px; margin-top: 8px; padding: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
            "QPushButton { padding: 7px 12px; }"
            "QPlainTextEdit { background: #0f172a; color: #e2e8f0;"
            "font-family: Consolas, monospace; }"
        )
        self._sync_controls()

    def selected_formats(self) -> tuple[str, ...]:
        return tuple(
            format_name
            for format_name, checkbox in self._format_checks.items()
            if checkbox.isChecked()
        )

    def _methods_for_selection(self) -> tuple[str, ...]:
        method = self.selected_method()
        return build.METHODS if method == "both" else (method,)

    def selected_method(self) -> str:
        return METHOD_LABELS[self.method_combo.currentText()]

    def build_arguments(self) -> list[str]:
        formats = self.selected_formats()
        if not formats:
            raise ValueError("Select at least one installer or archive format.")
        output = self.output_edit.text().strip()
        if not output:
            raise ValueError("Choose an output folder.")
        args = [
            str(build.ROOT / "build.py"),
            "--method",
            self.selected_method(),
            "--output",
            str(Path(output).expanduser()),
        ]
        for format_name in formats:
            args.extend(("--format", format_name))
        return args

    def _set_all_formats(self, checked: bool) -> None:
        for checkbox in self._format_checks.values():
            checkbox.setChecked(checked)

    def _sync_controls(self) -> None:
        busy = self._process is not None
        has_selection = bool(self.selected_formats())
        self.build_button.setEnabled(not busy and has_selection)
        self.method_combo.setEnabled(not busy)
        self.output_edit.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)
        self.select_all_button.setEnabled(not busy)
        self.select_none_button.setEnabled(not busy)
        for checkbox in self._format_checks.values():
            checkbox.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def _browse_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose build output folder",
            self.output_edit.text() or str(build.ROOT),
        )
        if selected:
            self.output_edit.setText(selected)

    def _start_build(self) -> None:
        try:
            build_args = self.build_arguments()
        except ValueError as exc:
            QMessageBox.warning(self, "Build options", str(exc))
            return

        formats = self.selected_formats()
        methods = self._methods_for_selection()
        missing_tools = build.missing_external_tools(
            self.target,
            methods,
            formats,
        )
        if missing_tools:
            lines = [
                "Install these native build tools and add them to PATH, then retry:"
            ]
            lines.extend(" - " + " or ".join(options) for options in missing_tools)
            QMessageBox.warning(
                self,
                "Missing platform tools",
                "\n".join(lines),
            )
            return

        missing_packages = build.missing_python_build_packages(methods)
        if missing_packages:
            answer = QMessageBox.question(
                self,
                "Install build dependencies?",
                "These Python build tools are missing:\n\n"
                + "\n".join(f" - {package}" for package in missing_packages)
                + "\n\nInstall the project's build requirements into the Python "
                "environment used to start this GUI?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._append_log("Installing Python build dependencies…")
            self._launch_process(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    str(build.ROOT / "requirements-build.txt"),
                ],
                phase="install",
                build_args=build_args,
            )
            return

        self._confirm_and_build(build_args)

    def _confirm_and_build(self, build_args: Sequence[str]) -> None:
        formats = ", ".join(self.selected_formats())
        method = self.method_combo.currentText()
        output = str(Path(self.output_edit.text()).expanduser())
        answer = QMessageBox.question(
            self,
            "Confirm build",
            f"Builder: {method}\n"
            f"Target: {self.target} ({build.normalized_architecture()})\n"
            f"Formats: {formats}\n"
            f"Output: {output}\n\n"
            "Start building now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._append_log(f"Starting {method} build for {self.target}…")
        self._launch_process(
            [sys.executable, *build_args],
            phase="build",
        )

    def _launch_process(
        self,
        command: Sequence[str],
        *,
        phase: str,
        build_args: Sequence[str] | None = None,
    ) -> None:
        process = QProcess(self)
        process.setWorkingDirectory(str(build.ROOT))
        process.setProgram(command[0])
        process.setArguments(list(command[1:]))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda process=process: self._read_output(process)
        )
        process.finished.connect(
            lambda exit_code, exit_status, process=process: self._process_finished(
                process,
                exit_code,
                exit_status,
                phase,
                build_args,
            )
        )
        process.errorOccurred.connect(
            lambda error, process=process: self._process_error(process, error)
        )
        self._process = process
        self._process_phase = phase
        self.status_label.setText(
            "Installing build requirements…" if phase == "install" else "Building…"
        )
        self._sync_controls()
        self._append_log("+ " + subprocess_display(command))
        process.start()

    def _read_output(self, process: QProcess) -> None:
        text = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if text:
            self._append_log(text.rstrip())

    def _process_finished(
        self,
        process: QProcess,
        exit_code: int,
        exit_status: QProcess.ExitStatus,
        phase: str,
        build_args: Sequence[str] | None,
    ) -> None:
        if process is not self._process:
            process.deleteLater()
            return
        self._read_output(process)
        process.deleteLater()
        self._process = None
        self._process_phase = ""
        self._sync_controls()

        if exit_status != QProcess.ExitStatus.NormalExit or exit_code != 0:
            self.status_label.setText(
                "Dependency installation failed."
                if phase == "install"
                else "Build failed. See output for details."
            )
            self._append_log(f"Process exited with code {exit_code}.")
            return
        if phase == "install":
            missing = build.missing_python_build_packages(
                self._methods_for_selection()
            )
            if missing:
                self.status_label.setText("Required build tools are still missing.")
                self._append_log("Still missing: " + ", ".join(missing))
                return
            self._confirm_and_build(build_args or [])
            return

        self.status_label.setText("Build completed successfully.")
        self._append_log("Build completed successfully.")

    def _process_error(self, process: QProcess, error: QProcess.ProcessError) -> None:
        if process is not self._process:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._append_log(
                "Could not start the process: " + process.errorString()
            )
            process.deleteLater()
            self._process = None
            self._process_phase = ""
            self._sync_controls()
            self.status_label.setText("Could not start the build process.")

    def _cancel_build(self) -> None:
        process = self._process
        if process is None:
            return
        self.status_label.setText("Cancelling…")
        process.kill()
        process.waitForFinished(3000)
        if self._process is process:
            process.deleteLater()
            self._process = None
            self._process_phase = ""
        self._sync_controls()
        self.status_label.setText("Build cancelled.")
        self._append_log("Build cancelled by user.")

    def _append_log(self, text: str) -> None:
        self.log_output.appendPlainText(text)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


def subprocess_display(command: Sequence[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def main(argv: Sequence[str] | None = None) -> int:
    app = QApplication(list(argv) if argv is not None else sys.argv)
    window = BuildWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
