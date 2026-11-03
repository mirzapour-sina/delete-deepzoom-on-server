---
name: building-and-deployment
description: Skill for building and deploying the Remote DeepZoom Folder Cleaner desktop application
---

# Building and Deployment

This skill covers building and deploying the Remote DeepZoom Folder Cleaner PySide6 desktop application.

## When to use

Use this skill when you need to:
- Build the application into a standalone executable
- Modify build scripts or configuration
- Package the app for distribution
- Troubleshoot build issues

## Build scripts

The project includes two build scripts:

- `build_app.bat` - Standard console build
- `build_app_gui.bat` - GUI build (no console window)

These are batch files for Windows. They likely use PyInstaller or Nuitka to package the application.

## Build process

The app entry point is `main.py`, which:
1. Creates a QGuiApplication
2. Creates a SessionManager and adds an initial session
3. Loads the QML file from `qml/Main.qml`
4. Sets initial properties on the QML engine (sessionManager)
5. Starts the application event loop

## Dependencies

Key dependencies (from the project):
- PySide6 (Qt for Python)
- paramiko (SSH client)

Install with:
```
pip install PySide6 paramiko
```

## Running the app

For development:
```
python main.py
```

Or run the test script:
```
python test_run.py
```

## Files to reference

- `main.py` - Application entry point
- `build_app.bat` - Console build script
- `build_app_gui.bat` - GUI build script
- `qml/Main.qml` - Main QML file loaded by the app
- `deepzoom_cleaner/` - Python package with backend, settings, session manager