# UI/UX Optimization Report — Remote DeepZoom Folder Cleaner

**Date:** 2026-10-27  
**Project:** Remote DeepZoom Folder Cleaner (PySide6 / QtQuick QML + Paramiko SSH)  
**Status of GUI run:** App launches cleanly to the "New SSH Session" connection screen. Full flow (file explorer, properties dialog) could not be exercised because it requires live SSH credentials to a Linux server.

---

## Summary

The application is well-structured with a modern, consistent color palette and a solid architecture (SessionManager + Backend per session, QML UI with property bindings). The core features all work at the code level: connect, browse, copy/cut/paste, delete, rename, compress/extract, edit, upload/download, disk usage, block devices, connection history, and an on-demand recursive folder-count properties dialog with streaming progress.

Below is a prioritized list of UI/UX optimizations observed from static code review and the running app, grouped by category.

---

## 1. Connection / Onboarding Experience (Highest Impact)

### a) Pre-fill last connection on startup
The `Settings` class persists `last_connection` (settings.py:110-112), but Main.qml never reads it to pre-fill the connection form. Every new session forces the user to re-type host/username/path.

**Fix:** In `Main.qml` `Component.onCompleted`, after loading connection history, set the form fields from `sessionManager.getLastConnection()` (expose it via SessionManager) or from `root.backend._settings`/`get_last_connection()`.

### b) Empty-state guidance
When no sessions exist, the welcome screen shows "New Session", "Load Saved Connection", and "Settings" buttons plus a recent-connections list. It's good, but there's no inline hint explaining what a "DeepZoom folder" is or that an SSH server with `python3` and `rm` is required. The README documents this, but the UI does not.

**Fix:** Add a short "What you need" hint box on the welcome screen listing: SSH access, `python3` on the server, trusted host key, absolute remote path.

### c) App window icon
The window title bar shows the default Python/tk icon rather than a branded icon. `build.py` already has a `create_icon()` function that generates a PNG, but `main.py` never sets `app.setWindowIcon(...)`.

**Fix:** In `main.py`, create/set the window icon from the generated PNG (or a bundled icon file) so the taskbar and window decorations are branded.

---

## 2. Properties Dialog & Recursive Counting (Recently Implemented — Polish Needed)

The properties dialog (FileExplorerView.qml:1524-1600) now has a "Show more"/"Show less" toggle and streaming `entryStatsProgress` updates. Several UX rough edges remain:

### a) Toggle label doesn't reflect collapsed state after loading
When the user clicks "Show more", `statsExpanded` is set to `true` and the button text becomes "Show less". But after the stats finish loading, `onEntryStatsLoaded` unconditionally sets `statsExpanded = true` (line 106), so clicking "Show less" then re-opening always shows the stats again — the user's collapse choice is not persisted for the current dialog lifetime.

**Fix:** Only set `statsExpanded = true` in `onEntryStatsLoaded`/`onEntryStatsProgress` when stats were just requested (i.e., when the button was "Show more"). Track a separate `statsUserCollapsed` flag.

### b) Counts appear instantly at 0 then jump
When "Show more" is clicked, `statsFilesInside`/`statsFoldersInside` are reset to 0 immediately (line 1548-1549), then stream in via progress events. This is good UX (progressive), but the row labels "Files inside / Folders inside / Items inside" only render when `statsFilesInside >= 0` (line 686), so they pop in abruptly.

**Fix:** Show a subtle placeholder row ("Counting…") while loading, or keep the section slot reserved with a skeleton so the dialog doesn't jump in height when counts arrive.

### c) No visual progress indication during counting
The `onEntryStatsProgress` handler sets `statsLoading = false` immediately (line 117), so the "Counting contents…" label (line 1567) is never actually visible to the user during the recursive walk — even though the walk may take seconds on a large DeepZoom tree.

**Fix:** Keep `statsLoading = true` until `onEntryStatsLoaded` fires, so the "Counting contents…" label shows during the walk. The progress numbers still update live via `onEntryStatsProgress`.

### d) Button disabled for non-folders but no hint
The toggle is `enabled: !statsLoading && root.itemProperties.kind === "Folder"` (line 1543). For files, the button is simply disabled with no explanation, which may confuse users.

**Fix:** Add a muted hint label "Contents stats only apply to folders" when the selected item is not a folder, or hide the toggle entirely for non-folders.

---

## 3. File Explorer List & Table

### a) No column sorting
The file list (FileExplorerView.qml:1172-1262) shows Name / Size / Modified / Type but clicking a column header does nothing. Users commonly want to sort by size or date.

**Fix:** Add sort-by-column on header click with ascending/descending indicators.

### b) No inline size/folder count in the list
The status bar shows aggregate "Files: N | Folders: M" for the current folder (line 1318-1323), but individual rows don't show folder contents counts. For a cleanup tool, knowing which folders are large is the primary use case.

**Fix:** Add an optional "Contents" column to the row delegate that shows recursive file/folder counts for folders (cached from `loadDirectoryStats`), with a small loading indicator.

### c) Empty-state text is slightly misleading
When `entryModel.count === 0 && !loadingFolder`, it shows "This folder is empty." but doesn't distinguish between "folder exists but empty" vs "path error". The `loadingFolder` overlay only shows during navigation.

**Fix:** Differentiate empty-folder vs error states with distinct messages and a retry/action hint.

---

## 4. Status Bar & Feedback

### a) Status bar info is static text
The bottom status bar shows selection count and clipboard state as plain Labels (line 1306-1335). There's no persistent, dismissible notification area for operation results beyond the toast.

**Fine as-is:** The toast notification (Main.qml:50-94) already handles non-blocking feedback well. No change needed, but consider making the status bar show the last operation result briefly.

---

## 5. Dialog Consistency

### a) Mixed dialog sizing and patterns
- Properties dialog: width 560, content width 520
- Compress/Extract/Rename/New Folder: width 440, content width 400
- Upload/Download: width 500, content width 460
- Editor: width 700, height 500

No consistent max-width or content-width standard. The Upload dialog is `modal: false` while others are `modal: true` — inconsistent.

**Fix:** Standardize dialog widths (e.g., 480 content width) and make Upload/Download modal too (or document why they're modeless).

### b) Download "Cancel" doesn't actually cancel the SFTP transfer
The download cancel button (line 2217-2244) just sets `downloading = false` and closes the dialog, but the SFTP `get` continues running on the backend thread. The user thinks it's cancelled but it isn't.

**Fix:** Wire the cancel to actually abort the SFTP transfer (track the SFTP handle and close it), or at least don't claim the download was cancelled.

---

## 6. Theme / Dark Mode

### a) Hard-coded light theme only
All colors are hard-coded light-theme values (`#f8fafc`, `#ffffff`, `#0f172a`, etc.). There is no dark theme toggle and no system-theme detection, despite `settings.py` having a `"theme": "system"` default that's never read.

**Fix:** Implement a theme property (light/dark/system) bound to a QML palette, persisted in settings, and toggleable from the Settings dialog.

---

## 7. Accessibility & Polish

### a) No keyboard shortcuts
No shortcuts for common actions: `Ctrl+L` (focus path bar), `Ctrl+A` (select all), `Delete` (delete selection), `F5` (refresh), `Enter` (open/navigate).

**Fix:** Add `Keys.onPressed` handlers on the file list and path field.

### b) Tooltip delays are long
`ToolTip.delay: 600` (Main.qml:368) is slower than the typical 300-500ms. Minor.

### c) No "Connect" on Enter in the connection form
The connection form fields don't submit on Enter; the user must click the Connect button.

**Fix:** Connect `onAccepted` of the last field (or the whole form) to `doConnect()`.

---

## 8. Performance / Correctness (backend, affects perceived UX)

### a) `loadDirectoryStats` blocks on full stdout read
`backend.py:_directory_stats` (line 1800-1814) uses `_run_remote` which calls `stdout.read()` — blocking until the entire recursive walk finishes. For a large DeepZoom tree this can take many seconds, freezing the "directory stats" operation with no progress UI. Note: `loadEntryStats` (the properties-dialog path) correctly uses streaming line-by-line reads, but `loadDirectoryStats` does not.

**Fix:** Refactor `loadDirectoryStats` to stream progress like `loadEntryStats`, or run it so the UI stays responsive.

### b) `busy` is a global lock
`_start_worker` (line 1891) rejects any new operation while `self._busy` is True. So the user can't refresh disk usage while a delete is running, etc. This makes the app feel sluggish under concurrent operations.

**Fix:** Allow independent operations (reads like disk usage, directory stats) to run concurrently with writes; only serialize operations that touch the same connection.

---

## 9. Build / Packaging

### a) Nuitka crash report committed
`nuitka-crash-report.xml` is an untracked artifact in the repo root. It's not a UI issue, but it indicates a prior build failure that was never cleaned up.

**Fix:** Remove from repo / add to `.gitignore`.

### b) No `.gitignore`
Untracked files like `output.txt`, `build_app.bat`, `nuitka-crash-report.xml`, `.venv/` are scattered in the repo root.

**Fix:** Add a `.gitignore` for `.venv/`, `build/`, `dist-packages/`, `*.txt` outputs, crash reports, and `.exe`/`.zip` artifacts.

---

## Recommended Priority Order

| Priority | Area | Change |
|----------|------|--------|
| P0 | Properties dialog | Keep `statsLoading = true` during streaming count so "Counting…" is visible; preserve user collapse choice |
| P0 | Onboarding | Pre-fill last connection from history on startup |
| P1 | App icon | Set `app.setWindowIcon()` from the generated PNG |
| P1 | File list | Add column sorting by Name/Size/Modified |
| P1 | Dialog consistency | Standardize widths; make Upload/Download modal |
| P2 | Download cancel | Actually abort SFTP transfer on cancel |
| P2 | Theme | Implement light/dark/system theme toggle |
| P2 | Backend | Stream `loadDirectoryStats` progress instead of blocking read |
| P3 | Accessibility | Add keyboard shortcuts (Ctrl+A, Delete, F5, Enter) |
| P3 | Empty states | Differentiate empty-folder vs error in file list |
| P3 | Build hygiene | Add `.gitignore`, remove crash report |

---

## Files Referenced

- `qml/FileExplorerView.qml` — file list, properties dialog, tree panel, status bar
- `qml/Main.qml` — app shell, toast, session stack, welcome screen
- `qml/SessionTab.qml` — per-session connection form + tab bar
- `qml/DiskUsageView.qml` — disk usage + block devices tables
- `deepzoom_cleaner/backend.py` — all SSH/backend operations, streaming stats
- `deepzoom_cleaner/session_manager.py` — multi-session management
- `deepzoom_cleaner/settings.py` — settings persistence
- `main.py` — app entry point
- `build.py`, `build_gui.py` — standalone installers
- `tests/test_backend.py` — backend unit tests (23 tests, all pass)
