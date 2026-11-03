"""Headless render check: load Main.qml and verify the UI loads without errors.

Runs with the offscreen platform plugin so no desktop screen capture is needed.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QTimer
from PySide6.QtQml import QQmlApplicationEngine
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    errors = []

    def on_warning(msg):
        errors.append(msg)

    engine.warnings.connect(on_warning)
    engine.load(ROOT / "qml" / "Main.qml")

    def finish():
        root_objects = engine.rootObjects()
        print("root objects:", len(root_objects))
        print("qml warnings/errors:", errors)
        if root_objects:
            root = root_objects[0]
            print("window title:", root.title())
            print("theme:", root.theme)
            print("session count:", root.sessionManager.getSessionCount())
            print("session manager:", root.sessionManager is not None)
        app.quit()

    QTimer.singleShot(1500, finish)
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
