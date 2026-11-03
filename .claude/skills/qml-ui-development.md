---
name: qml-ui-development
description: Skill for working with PySide6/QML views, dialogs, file explorers, and UI components in the Remote DeepZoom Folder Cleaner app
---

# QML UI Development

This skill covers working with the QML frontend of the Remote DeepZoom Folder Cleaner app. The app uses PySide6 with QtQuick 2.15, QtQuick.Controls 2.15, QtQuick.Layouts 1.15, and Qt.labs.platform.

## When to use

Use this skill when you need to:
- Modify QML views (FileExplorerView.qml, SessionTab.qml, Main.qml, DiskUsageView.qml, DeleteFoldersView.qml)
- Add or modify FileDialog, Dialog, or other QtQuick components
- Change UI layout, styling, or behavior
- Work with toast notifications, confirm dialogs, or status bars
- Modify signal/slot connections between QML and Python backend

## Project structure

```
qml/
  Main.qml          - Main application window, session tabs, toast notification
  SessionTab.qml    - Individual session tab with connection form and toolbar
  FileExplorerView.qml - File explorer with upload/download/delete/rename/compress
  DiskUsageView.qml - Disk usage and block devices view
  DeleteFoldersView.qml - Folder deletion view
```

## Key patterns

### Backend integration
QML files receive a `backend` property (Backend instance) and communicate via PySide6 signals/slots. Common backend signals:
- `entriesLoaded(path, entries)` - file/folder listing loaded
- `connectionStatusChanged(status, message)` - connection state changed
- `uploadCompleted(remote_path, success, message)` - upload finished
- `downloadCompleted(local_path, success, message)` - download finished
- `errorOccurred(message)` - error to display as toast

### Toast notifications
Main.qml has a `toastNotification` Rectangle at top-center. Use `root.requestNotice(message)` or `window.showNotice(message)` to show non-blocking toasts.

### FileDialog
Both upload and download use `Qt.labs.platform.FileDialog` (native file dialogs). They are placed at root level of FileExplorerView.qml to avoid Column layout issues.

### Hidden files
Hidden file visibility is controlled by `showHidden` property, initialized from `backend.showHiddenFiles()` in `Component.onCompleted` and persisted via `backend.setShowHiddenFiles(bool)`.

## Common tasks

### Add a new QML view
1. Create the .qml file in the qml/ directory
2. Import QtQuick 2.15, QtQuick.Controls 2.15, QtQuick.Layouts 1.15
3. Add the view to Main.qml's StackLayout or as a separate dialog
4. Wire up backend signals if needed

### Modify a FileDialog
FileDialogs are defined at root level of FileExplorerView.qml:
- `uploadFileDialog` - Platform.FileDialog for selecting files to upload
- `downloadFileDialog` - Platform.FileDialog with `selectFolder: true` for choosing save location

Set `folder` property before calling `open()` to initialize the dialog's starting directory.

### Add a backend signal to QML
1. Add the signal to the Backend class in deepzoom_cleaner/backend.py
2. Connect the signal in QML using `Connections { target: backend; onSignalName: ... }`
3. Or connect programmatically in Component.onCompleted

## Files to reference

- `deepzoom_cleaner/backend.py` - Backend signals and slots
- `qml/Main.qml` - Main window, toast notification, session management
- `qml/FileExplorerView.qml` - File explorer UI with FileDialogs
- `deepzoom_cleaner/settings.py` - Settings persistence