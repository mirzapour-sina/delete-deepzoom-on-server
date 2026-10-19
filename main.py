import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from deepzoom_cleaner.backend import Backend


def main() -> int:
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    backend = Backend()
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        app_dir = Path(sys.executable).resolve().parent
    else:
        app_dir = Path(__file__).resolve().parent
    qml_file = app_dir / "qml" / "Main.qml"
    engine.load(qml_file)

    if not engine.rootObjects():
        return 1
    engine.rootObjects()[0].setProperty("backend", backend)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
