import os
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

from deepzoom_cleaner.session_manager import SessionManager


def main() -> int:
    app = QGuiApplication(sys.argv)
    icon_path = Path(__file__).resolve().parent / "deepzoom_cleaner" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    engine = QQmlApplicationEngine()

    # Create session manager
    session_manager = SessionManager()
    session_manager.addSession()  # Create initial session

    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        app_dir = Path(sys.executable).resolve().parent
    else:
        app_dir = Path(__file__).resolve().parent

    qml_file = app_dir / "qml" / "Main.qml"

    # Set initial properties BEFORE loading so Component.onCompleted can use them
    engine.setInitialProperties({"sessionManager": session_manager})
    engine.load(qml_file)

    if not engine.rootObjects():
        return 1

    # Cleanup on exit
    app.aboutToQuit.connect(session_manager.cleanup)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())