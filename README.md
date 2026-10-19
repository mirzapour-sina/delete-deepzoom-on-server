# Remote DeepZoom Folder Cleaner

A Python + QML desktop app for browsing a Linux server over SSH and permanently
removing selected subfolders. Deletions run on the server with `rm -rf`; tile
files are never transferred to the desktop.

## Requirements

- Python 3.10 or newer
- SSH access to the Linux server
- The server must provide `python3` for folder listing and `rm` for deletion
- The server's SSH host key must already be trusted in your local
  `~/.ssh/known_hosts` file, or explicitly verified and trusted in the app

## Install and run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

On Linux or macOS, activate the environment with
`source .venv/bin/activate` instead.

Enter the server address, username, and an absolute Linux path containing the
DeepZoom folders. Authentication can use an SSH agent/default key, a selected
private key file, or a password. For an unknown SSH host key, the app shows its
SHA-256 fingerprint and asks whether to trust it. Verify that fingerprint with
your server administrator through a separate trusted channel before accepting.
Accepted keys are saved in the user's home folder under
`.deepzoom-cleaner/known_hosts`; a later key change is rejected.

Folder names are read as Unicode and shown with their full remote paths. Choose
folders with the checkboxes and confirm before removal. Up to four selected
folders are removed concurrently. For each folder, the server's native
`rm -rf --` removes its contents in place, which avoids transferring or
enumerating millions of tile files on the desktop.

Deletion is permanent. Verify the server and parent path carefully before
confirming.

## Build standalone installers

The app includes a reusable build script for PyInstaller and Nuitka. Build
requirements are separate from normal run-time requirements:

```powershell
python -m pip install -r requirements-build.txt
python build.py
```

For a graphical builder instead, run:

```powershell
python build_gui.py
```

or launch it from the build script with `python build.py --gui`.
The window has the same method, platform-available format, output folder, and
confirmation options as the interactive CLI. It also streams the build log,
supports cancelling a running process, checks native packaging tools before
building, and asks before installing missing Python build dependencies.

With no arguments, the interactive CLI offers PyInstaller, Nuitka, or both;
lets you pick one or more installer/archive formats supported by the current
OS; asks where to write the artifacts; checks for required native tools; and
offers to install missing Python build dependencies. Review the summary and
confirm to start. Enter comma-separated format numbers to choose several, `0`
for all formats on this OS, or `q` at any menu to cancel. Use `python build.py
--interactive` to open the same menu explicitly.

For unattended/repeatable builds, the equivalent command-line options remain
available:

```powershell
python build.py --list
python build.py --method pyinstaller --format all
python build.py --method nuitka --format portable
python build.py --method both --format portable
```

`--method` accepts `pyinstaller`, `nuitka`, or `both`. Repeat `--format` to
choose multiple outputs; omit it or use `--format all` to build every format
available on the current OS. Use `--output PATH` to change the output folder.
Packages are written beneath `dist-packages/<os>/<builder>/`.

| Build OS | Formats from `--format all` |
| --- | --- |
| Windows | Portable ZIP, Inno Setup `.exe`, WiX `.msi` |
| Linux | Portable ZIP, AppImage, Debian `.deb` |
| macOS | Portable ZIP containing an `.app`, `.dmg`, `.pkg` |

Each native installer includes the Python runtime and application libraries
collected by the selected builder. Build for each target operating system on
that OS; PyInstaller and Nuitka do not cross-compile these packages. The
`Build standalone packages` GitHub Actions workflow runs both builders on
Windows, Linux, and macOS and uploads their artifacts when manually started or
when a `v*` tag is pushed.

### Platform build tools and limitations

- Windows installers require Inno Setup (`ISCC`) and WiX v4+ (`wix`) in `PATH`.
- Linux AppImage output requires `linuxdeploy`; Debian packages require
  `dpkg-deb` (typically provided by `dpkg`).
- macOS `.dmg` and `.pkg` use Apple's `hdiutil` and `pkgbuild` tools.
- Nuitka needs a native C compiler. Use Visual Studio Build Tools on Windows,
  Xcode command-line tools on macOS, and GCC/Clang on Linux.
- The Windows MSI installer currently targets x64. Builds otherwise use the
  architecture of the active Python environment and native build host.
- AppImage/standalone Linux builds can still depend on system-provided
  libraries and a compatible glibc. macOS distribution outside your own
  machines may require Apple signing and notarization, which this unsigned
  builder does not perform.
