import os
os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'
import sys
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from PySide6.QtQml import QQmlApplicationEngine
from pathlib import Path
from deepzoom_cleaner.session_manager import SessionManager


def handler(mode, context, message):
    print(f"[QML/{context.category}] {message}", file=sys.stderr)


qInstallMessageHandler(handler)

app = QGuiApplication(sys.argv)
engine = QQmlApplicationEngine()
session_manager = SessionManager()
session_manager.addSession()

app_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
qml_file = app_dir / 'qml' / 'Main.qml'
print('Loading:', qml_file)

# Set initial properties BEFORE loading so Component.onCompleted can use them
engine.setInitialProperties({'sessionManager': session_manager})
engine.load(qml_file)

if not engine.rootObjects():
    print('No root objects!')
    sys.exit(1)

root = engine.rootObjects()[0]
print('App started successfully')
app.aboutToQuit.connect(session_manager.cleanup)
sys.exit(app.exec())