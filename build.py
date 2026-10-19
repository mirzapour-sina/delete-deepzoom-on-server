from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable, Sequence
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parent
APP_NAME = "DeepZoomCleaner"
DISPLAY_NAME = "Remote DeepZoom Folder Cleaner"
VERSION = "1.0.0"
METHODS = ("pyinstaller", "nuitka")
FORMATS = ("portable", "inno", "msi", "appimage", "deb", "dmg", "pkg")
PLATFORM_FORMATS = {
    "windows": ("portable", "inno", "msi"),
    "linux": ("portable", "appimage", "deb"),
    "macos": ("portable", "dmg", "pkg"),
}
WIX_NAMESPACE = "http://wixtoolset.org/schemas/v4/wxs"


def current_platform(system: str | None = None) -> str:
    value = (system or platform.system()).lower()
    platforms = {"windows": "windows", "linux": "linux", "darwin": "macos"}
    try:
        return platforms[value]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported build platform: {value}") from exc


def normalized_architecture(machine: str | None = None) -> str:
    value = (machine or platform.machine()).lower()
    return {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(value, value)


def selected_formats(target: str, choices: Sequence[str] | None) -> tuple[str, ...]:
    supported = PLATFORM_FORMATS[target]
    if not choices or "all" in choices:
        if choices and len(choices) > 1:
            raise ValueError("'all' cannot be combined with individual formats.")
        return supported
    invalid = [choice for choice in choices if choice not in supported]
    if invalid:
        raise ValueError(
            f"{', '.join(invalid)} are not available for {target}. "
            f"Choose from: {', '.join(supported)}."
        )
    return tuple(dict.fromkeys(choices))


def missing_python_build_packages(methods: Sequence[str]) -> list[str]:
    modules = {
        "pyinstaller": ("PyInstaller", "PyInstaller"),
        "nuitka": ("nuitka", "Nuitka"),
    }
    return [
        package
        for method in methods
        for module, package in (modules[method],)
        if importlib.util.find_spec(module) is None
    ]


def required_external_tools(
    target: str,
    methods: Sequence[str],
    formats: Sequence[str],
) -> tuple[tuple[str, ...], ...]:
    requirements: list[tuple[str, ...]] = []
    if "nuitka" in methods:
        compiler = {
            "windows": ("cl",),
            "linux": ("cc", "gcc", "clang"),
            "macos": ("clang",),
        }[target]
        requirements.append(compiler)
    tool_by_format = {
        "inno": ("ISCC.exe", "ISCC"),
        "msi": ("wix.exe", "wix"),
        "appimage": (
            "linuxdeploy",
            f"linuxdeploy-{normalized_architecture()}.AppImage",
        ),
        "deb": ("dpkg-deb",),
        "dmg": ("hdiutil",),
        "pkg": ("pkgbuild",),
    }
    requirements.extend(
        tool_by_format[format_name]
        for format_name in formats
        if format_name in tool_by_format
    )
    return tuple(requirements)


def missing_external_tools(
    target: str,
    methods: Sequence[str],
    formats: Sequence[str],
    which: Callable[[str], str | None] = shutil.which,
) -> list[tuple[str, ...]]:
    return [
        alternatives
        for alternatives in required_external_tools(target, methods, formats)
        if not any(which(name) for name in alternatives)
    ]


def install_python_build_requirements() -> None:
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(ROOT / "requirements-build.txt"),
        ]
    )


def ensure_python_build_packages(
    methods: Sequence[str],
    *,
    interactive: bool,
    input_fn: Callable[[str], str] | None = None,
    print_fn: Callable[..., None] = print,
) -> None:
    missing = missing_python_build_packages(methods)
    if not missing:
        return
    names = ", ".join(missing)
    if not interactive:
        raise RuntimeError(
            f"Missing Python build tools: {names}. "
            "Install them with: python -m pip install -r requirements-build.txt"
        )
    print_fn(f"Python build tools not installed: {names}.")
    answer = (input_fn or input)(
        "Install project and build dependencies now? [y/N]: "
    ).strip().lower()
    if answer not in ("y", "yes"):
        raise RuntimeError(
            "Build cancelled because required Python build tools are missing."
        )
    install_python_build_requirements()
    still_missing = missing_python_build_packages(methods)
    if still_missing:
        raise RuntimeError(
            "Build dependencies are still missing after installation: "
            + ", ".join(still_missing)
        )


def ensure_external_build_tools(
    target: str,
    methods: Sequence[str],
    formats: Sequence[str],
    *,
    print_fn: Callable[..., None] = print,
) -> None:
    missing = missing_external_tools(target, methods, formats)
    if not missing:
        return
    print_fn("Install the missing platform build tools, then run the builder again:")
    for alternatives in missing:
        print_fn("  - " + " or ".join(alternatives))
    raise RuntimeError(
        "A required native compiler or installer tool is not available in PATH."
    )


def _prompt_index(
    title: str,
    options: Sequence[tuple[str, str]],
    *,
    input_fn: Callable[[str], str],
    print_fn: Callable[..., None],
) -> int | None:
    print_fn(title)
    for index, (name, description) in enumerate(options, start=1):
        print_fn(f"  {index}. {name} - {description}")
    print_fn("  q. Cancel")
    while True:
        answer = input_fn("> ").strip().lower()
        if answer in ("q", "quit", "cancel"):
            return None
        try:
            selected = int(answer)
        except ValueError:
            selected = 0
        if 1 <= selected <= len(options):
            return selected - 1
        print_fn(f"Choose a number from 1 to {len(options)}, or q to cancel.")


def interactive_configuration(
    *,
    target: str | None = None,
    input_fn: Callable[[str], str] | None = None,
    print_fn: Callable[..., None] = print,
) -> argparse.Namespace | None:
    read_input = input_fn or input
    target = target or current_platform()
    print_fn(f"{DISPLAY_NAME} - interactive builder")
    print_fn(f"Build target: {target} ({normalized_architecture()})")
    print_fn("Native installers must be built on the operating system they target.")

    method_options = (
        ("PyInstaller", "build a standalone application directory"),
        ("Nuitka", "compile a standalone application"),
        ("Both", "run both builders"),
    )
    method_index = _prompt_index(
        "Choose a build method:",
        method_options,
        input_fn=read_input,
        print_fn=print_fn,
    )
    if method_index is None:
        return None
    method = ("pyinstaller", "nuitka", "both")[method_index]

    available_formats = PLATFORM_FORMATS[target]
    print_fn("Choose installer/archive formats (enter numbers separated by commas):")
    print_fn("  0. All formats available on this OS")
    for index, format_name in enumerate(available_formats, start=1):
        descriptions = {
            "portable": "portable ZIP archive",
            "inno": "Windows installer (.exe)",
            "msi": "Windows Installer package (.msi)",
            "appimage": "Linux AppImage",
            "deb": "Debian/Ubuntu package (.deb)",
            "dmg": "macOS disk image (.dmg)",
            "pkg": "macOS installer (.pkg)",
        }
        print_fn(f"  {index}. {format_name} - {descriptions[format_name]}")
    print_fn("  q. Cancel")
    while True:
        answer = read_input("> ").strip().lower()
        if answer in ("q", "quit", "cancel"):
            return None
        if answer in ("0", "all"):
            formats = available_formats
            break
        try:
            selected_indices = [int(part.strip()) for part in answer.split(",")]
        except ValueError:
            selected_indices = []
        if selected_indices and all(
            1 <= index <= len(available_formats) for index in selected_indices
        ):
            formats = tuple(
                dict.fromkeys(available_formats[index - 1] for index in selected_indices)
            )
            break
        print_fn(
            "Enter 0 for all, a comma-separated list of valid numbers, or q to cancel."
        )

    default_output = ROOT / "dist-packages"
    output_answer = read_input(
        f"Output directory [{default_output}] (or q to cancel): "
    ).strip()
    if output_answer.lower() in ("q", "quit", "cancel"):
        return None
    output = Path(output_answer).expanduser() if output_answer else default_output

    methods = METHODS if method == "both" else (method,)
    print_fn("\nSelected build:")
    print_fn(f"  Method: {method}")
    print_fn(f"  Formats: {', '.join(formats)}")
    print_fn(f"  Output: {output}")
    if target in ("windows", "linux", "macos"):
        print_fn(
            "  Native build host: "
            f"{target} ({normalized_architecture()})"
        )
    confirmation = _prompt_index(
        "Start this build?",
        (("Build", "continue"), ("Cancel", "return without building")),
        input_fn=read_input,
        print_fn=print_fn,
    )
    if confirmation != 0:
        return None

    return argparse.Namespace(
        method=method,
        formats=formats,
        output=output,
        target=target,
        methods=methods,
        interactive=True,
    )


def run(command: Sequence[str], *, cwd: Path = ROOT) -> None:
    print("+", subprocess.list2cmdline([str(part) for part in command]))
    subprocess.run(command, cwd=cwd, check=True)


def find_tool(*names: str) -> str:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError(
        f"Required build tool not found ({' or '.join(names)}). "
        "Install it using the platform-specific instructions in README.md."
    )


def remove_if_present(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def executable_name(target: str) -> str:
    return APP_NAME + (".exe" if target == "windows" else "")


def normalize_bundle(source: Path, destination: Path, target: str) -> Path:
    if not source.is_dir():
        raise RuntimeError(f"Standalone build directory not found: {source}")
    remove_if_present(destination)
    shutil.copytree(source, destination)
    wanted = executable_name(target)
    candidates = (
        destination / "main.exe",
        destination / "main",
        destination / "main.bin",
    )
    for candidate in candidates:
        if candidate.exists() and candidate.name != wanted:
            candidate.rename(destination / wanted)
            break
    if not (destination / wanted).is_file():
        raise RuntimeError(f"Could not find the built application executable in {source}.")
    return destination


def create_icon(destination: Path) -> None:
    import struct
    import zlib

    size = 256
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            inside = 32 <= x < 224 and 32 <= y < 224
            tile = inside and (
                x < 96 or x >= 160 or y < 96 or y >= 160
            )
            rows.extend((37, 99, 235, 255) if tile else (219, 234, 254, 255))

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )
    destination.write_bytes(png)


def build_pyinstaller(build_root: Path, target: str) -> Path:
    output = build_root / "pyinstaller"
    work = build_root / "pyinstaller-work"
    remove_if_present(output)
    remove_if_present(work)
    separator = ";" if target == "windows" else ":"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        APP_NAME,
        "--distpath",
        str(output),
        "--workpath",
        str(work),
        "--add-data",
        f"{ROOT / 'qml'}{separator}qml",
        "--collect-all",
        "PySide6",
        "--collect-all",
        "paramiko",
        "--collect-all",
        "cryptography",
    ]
    if target in ("windows", "macos"):
        command.append("--windowed")
    command.append(str(ROOT / "main.py"))
    run(command)
    bundle = output / f"{APP_NAME}.app" if target == "macos" else output / APP_NAME
    expected_executable = (
        bundle / "Contents" / "MacOS" / executable_name(target)
        if target == "macos"
        else bundle / executable_name(target)
    )
    if not expected_executable.is_file():
        raise RuntimeError(
            "PyInstaller finished without the expected executable. "
            "Check that the selected environment has PyInstaller installed."
        )
    return bundle


def build_nuitka(build_root: Path, target: str) -> Path:
    output = build_root / "nuitka"
    remove_if_present(output)
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=standalone",
        "--enable-plugin=pyside6",
        f"--include-data-dir={ROOT / 'qml'}=qml",
        "--include-package=paramiko",
        "--include-package=cryptography",
        f"--output-dir={output}",
        f"--output-filename={APP_NAME}",
    ]
    if target == "windows":
        command.append("--windows-console-mode=disable")
    if target == "macos":
        command.append("--macos-create-app-bundle")
    command.append(str(ROOT / "main.py"))
    run(command)
    if target == "macos":
        candidates = sorted(output.glob("*.app"))
        if len(candidates) != 1:
            raise RuntimeError(
                f"Expected one Nuitka macOS app bundle in {output}, found {len(candidates)}."
            )
        return candidates[0]
    candidates = sorted(output.glob("*.dist"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one Nuitka standalone directory in {output}, found {len(candidates)}."
        )
    bundle_parent = build_root / "nuitka-bundle"
    return normalize_bundle(candidates[0], bundle_parent, target)


def write_archive(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in source.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(source.parent))
    return destination


def create_inno_installer(bundle: Path, output: Path) -> Path:
    compiler = find_tool("ISCC.exe", "ISCC")
    output.mkdir(parents=True, exist_ok=True)
    setup_script = output.parent / "DeepZoomCleaner.iss"
    source_path = str(bundle.resolve()).replace('"', '""')
    output_path = str(output.resolve()).replace('"', '""')
    setup_script.write_text(
        f'''#define AppSource "{source_path}"
#define AppOutput "{output_path}"

[Setup]
AppId={{{{A264EB5B-516E-4A4C-9348-9816B8780001}}
AppName={DISPLAY_NAME}
AppVersion={VERSION}
DefaultDirName={{autopf}}\\{DISPLAY_NAME}
DefaultGroupName={DISPLAY_NAME}
OutputDir={{#AppOutput}}
OutputBaseFilename=DeepZoomCleaner-Setup
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={{app}}\\{APP_NAME}.exe
PrivilegesRequired=admin

[Files]
Source: "{{#AppSource}}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\{DISPLAY_NAME}"; Filename: "{{app}}\\{APP_NAME}.exe"
Name: "{{autodesktop}}\\{DISPLAY_NAME}"; Filename: "{{app}}\\{APP_NAME}.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
''',
        encoding="utf-8",
    )
    run([compiler, str(setup_script)])
    return output / "DeepZoomCleaner-Setup.exe"


def add_wix_files(
    bundle: Path, directory: ElementTree.Element, root: ElementTree.Element
) -> None:
    group = ElementTree.SubElement(root, f"{{{WIX_NAMESPACE}}}ComponentGroup", {"Id": "AppFiles"})
    directory_ids: dict[Path, str] = {bundle: "INSTALLFOLDER"}
    for file_path in sorted(path for path in bundle.rglob("*") if path.is_file()):
        relative_parent = file_path.parent.relative_to(bundle)
        current_path = bundle
        parent_id = "INSTALLFOLDER"
        for part in relative_parent.parts:
            current_path /= part
            if current_path not in directory_ids:
                directory_id = f"DIR{len(directory_ids)}"
                ElementTree.SubElement(
                    next(
                        node
                        for node in directory.iter()
                        if node.attrib.get("Id") == parent_id
                    ),
                    f"{{{WIX_NAMESPACE}}}Directory",
                    {"Id": directory_id, "Name": part},
                )
                directory_ids[current_path] = directory_id
            parent_id = directory_ids[current_path]
        component_id = f"COMP{len(directory_ids)}_{len(group)}"
        component = ElementTree.SubElement(
            group,
            f"{{{WIX_NAMESPACE}}}Component",
            {"Id": component_id, "Directory": parent_id, "Guid": "*"},
        )
        file_element = ElementTree.SubElement(
            component,
            f"{{{WIX_NAMESPACE}}}File",
            {
                "Id": f"FILE{len(group)}",
                "Source": str(file_path.resolve()),
                "KeyPath": "yes",
            },
        )
        if file_path.name == executable_name(current_platform()):
            ElementTree.SubElement(
                file_element,
                f"{{{WIX_NAMESPACE}}}Shortcut",
                {
                    "Id": "ApplicationShortcut",
                    "Name": DISPLAY_NAME,
                    "Target": f"[{parent_id}]{file_path.name}",
                    "WorkingDirectory": parent_id,
                },
            )


def create_msi_installer(bundle: Path, output: Path) -> Path:
    wix = find_tool("wix.exe", "wix")
    output.mkdir(parents=True, exist_ok=True)
    source = ElementTree.Element(
        f"{{{WIX_NAMESPACE}}}Wix",
    )
    package = ElementTree.SubElement(
        source,
        f"{{{WIX_NAMESPACE}}}Package",
        {
            "Name": DISPLAY_NAME,
            "Manufacturer": "DeepZoom Cleaner",
            "Version": VERSION,
            "UpgradeCode": "A264EB5B-516E-4A4C-9348-9816B8780002",
            "Scope": "perMachine",
        },
    )
    ElementTree.SubElement(
        package, f"{{{WIX_NAMESPACE}}}MediaTemplate", {"EmbedCab": "yes"}
    )
    standard = ElementTree.SubElement(
        package, f"{{{WIX_NAMESPACE}}}StandardDirectory", {"Id": "ProgramFiles64Folder"}
    )
    install = ElementTree.SubElement(
        standard,
        f"{{{WIX_NAMESPACE}}}Directory",
        {"Id": "INSTALLFOLDER", "Name": DISPLAY_NAME},
    )
    fragment = ElementTree.SubElement(source, f"{{{WIX_NAMESPACE}}}Fragment")
    add_wix_files(bundle, install, fragment)
    feature = ElementTree.SubElement(
        package,
        f"{{{WIX_NAMESPACE}}}Feature",
        {"Id": "MainFeature", "Title": DISPLAY_NAME, "Level": "1"},
    )
    ElementTree.SubElement(
        feature, f"{{{WIX_NAMESPACE}}}ComponentGroupRef", {"Id": "AppFiles"}
    )
    source_file = output.parent / "DeepZoomCleaner.wxs"
    ElementTree.ElementTree(source).write(source_file, encoding="utf-8", xml_declaration=True)
    destination = output / "DeepZoomCleaner.msi"
    run([wix, "build", str(source_file), "-arch", "x64", "-o", str(destination)])
    return destination


def create_deb_installer(bundle: Path, output: Path) -> Path:
    dpkg_deb = find_tool("dpkg-deb")
    package_root = output.parent / "deb-root"
    remove_if_present(package_root)
    app_dir = package_root / "usr" / "lib" / "deepzoom-cleaner"
    app_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle, app_dir)
    executable = executable_name("linux")
    launcher = package_root / "usr" / "bin" / "deepzoom-cleaner"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(
        f"#!/bin/sh\nexec /usr/lib/deepzoom-cleaner/{executable} \"$@\"\n",
        encoding="utf-8",
        newline="\n",
    )
    launcher.chmod(0o755)
    desktop = package_root / "usr" / "share" / "applications" / "deepzoom-cleaner.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={DISPLAY_NAME}\n"
        "Exec=deepzoom-cleaner\n"
        "Terminal=false\n"
        "Categories=Utility;\n",
        encoding="utf-8",
        newline="\n",
    )
    control = package_root / "DEBIAN" / "control"
    control.parent.mkdir(parents=True, exist_ok=True)
    architecture = {
        "x86_64": "amd64",
        "aarch64": "arm64",
    }.get(normalized_architecture(), normalized_architecture())
    control.write_text(
        f"Package: deepzoom-cleaner\n"
        f"Version: {VERSION}\n"
        f"Architecture: {architecture}\n"
        f"Maintainer: DeepZoom Cleaner\n"
        f"Description: {DISPLAY_NAME}\n",
        encoding="utf-8",
        newline="\n",
    )
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"deepzoom-cleaner_{VERSION}_{architecture}.deb"
    run([dpkg_deb, "--build", "--root-owner-group", str(package_root), str(destination)])
    return destination


def create_appimage(bundle: Path, output: Path) -> Path:
    appimage_arch = normalized_architecture()
    if appimage_arch not in ("x86_64", "aarch64"):
        raise RuntimeError(f"Unsupported AppImage architecture: {appimage_arch}")
    linuxdeploy = find_tool("linuxdeploy", f"linuxdeploy-{appimage_arch}.AppImage")
    app_dir = output.parent / "DeepZoomCleaner.AppDir"
    remove_if_present(app_dir)
    app_dir.mkdir(parents=True)
    binary_dir = app_dir / "usr" / "bin"
    shutil.copytree(bundle, binary_dir)
    executable = binary_dir / executable_name("linux")
    desktop = app_dir / f"{APP_NAME}.desktop"
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={DISPLAY_NAME}\n"
        f"Exec={executable_name('linux')}\n"
        "Terminal=false\n"
        "Categories=Utility;\n",
        encoding="utf-8",
        newline="\n",
    )
    icon = app_dir / f"{APP_NAME}.png"
    create_icon(icon)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{APP_NAME}-{appimage_arch}.AppImage"
    environment = os.environ.copy()
    environment.setdefault("APPIMAGE_EXTRACT_AND_RUN", "1")
    command = [
        linuxdeploy,
        "--appdir",
        str(app_dir),
        "--executable",
        str(executable),
        "--desktop-file",
        str(desktop),
        "--icon-file",
        str(icon),
        "--output",
        "appimage",
    ]
    print("+", subprocess.list2cmdline(command))
    subprocess.run(
        command,
        cwd=output,
        env=environment,
        check=True,
    )
    generated = destination
    if not generated.is_file():
        alternatives = sorted(output.glob("*.AppImage"))
        if len(alternatives) != 1:
            raise RuntimeError("linuxdeploy did not produce exactly one AppImage.")
        generated = alternatives[0]
    if generated != destination:
        generated.replace(destination)
    return destination


def make_macos_app(bundle: Path, output: Path) -> Path:
    app = output / f"{DISPLAY_NAME}.app"
    remove_if_present(app)
    if bundle.suffix == ".app":
        shutil.copytree(bundle, app)
        return app
    macos = app / "Contents" / "MacOS"
    macos.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle, macos)
    info = {
        "CFBundleName": DISPLAY_NAME,
        "CFBundleDisplayName": DISPLAY_NAME,
        "CFBundleIdentifier": "com.deepzoom.cleaner",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": executable_name("macos"),
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    }
    with (app / "Contents" / "Info.plist").open("wb") as file:
        plistlib.dump(info, file)
    return app


def create_dmg(app: Path, output: Path) -> Path:
    hdiutil = find_tool("hdiutil")
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "DeepZoomCleaner.dmg"
    run(
        [
            hdiutil,
            "create",
            "-volname",
            DISPLAY_NAME,
            "-srcfolder",
            str(app),
            "-ov",
            "-format",
            "UDZO",
            str(destination),
        ]
    )
    return destination


def create_pkg(app: Path, output: Path) -> Path:
    pkgbuild = find_tool("pkgbuild")
    output.mkdir(parents=True, exist_ok=True)
    destination = output / "DeepZoomCleaner.pkg"
    run(
        [
            pkgbuild,
            "--root",
            str(app.parent),
            "--install-location",
            "/Applications",
            "--identifier",
            "com.deepzoom.cleaner",
            "--version",
            VERSION,
            str(destination),
        ]
    )
    return destination


def create_artifacts(bundle: Path, target: str, formats: Sequence[str], output: Path) -> list[Path]:
    artifacts: list[Path] = []
    if "portable" in formats:
        portable = output / "portable"
        portable.mkdir(parents=True, exist_ok=True)
        source = make_macos_app(bundle, portable) if target == "macos" else bundle
        artifacts.append(
            write_archive(
                source,
                portable / f"{APP_NAME}-{target}-{normalized_architecture()}.zip",
            )
        )
    if "inno" in formats:
        artifacts.append(create_inno_installer(bundle, output / "inno"))
    if "msi" in formats:
        artifacts.append(create_msi_installer(bundle, output / "msi"))
    if "appimage" in formats:
        artifacts.append(create_appimage(bundle, output / "appimage"))
    if "deb" in formats:
        artifacts.append(create_deb_installer(bundle, output / "deb"))
    if "dmg" in formats or "pkg" in formats:
        macos_dir = output / "macos"
        app = make_macos_app(bundle, macos_dir)
        if "dmg" in formats:
            artifacts.append(create_dmg(app, output / "dmg"))
        if "pkg" in formats:
            artifacts.append(create_pkg(app, output / "pkg"))
    return artifacts


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build standalone DeepZoom Cleaner packages for this operating system."
    )
    parser.add_argument(
        "--method",
        choices=(*METHODS, "both"),
        default="pyinstaller",
        help="Executable builder to use (default: pyinstaller).",
    )
    parser.add_argument(
        "--format",
        dest="formats",
        action="append",
        choices=(*FORMATS, "all"),
        help="Installer/archive format; repeat to select multiple (default: all formats for this OS).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist-packages",
        help="Output directory (default: dist-packages).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available builders and this system's package formats.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run the interactive builder menu.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Open the graphical build options window.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if "--gui" in raw_args:
        from build_gui import main as gui_main

        return gui_main([sys.argv[0]])
    interactive = not raw_args or "--interactive" in raw_args
    if interactive:
        try:
            args = interactive_configuration()
        except (EOFError, KeyboardInterrupt):
            print("\nBuild cancelled.")
            return 0
        if args is None:
            print("Build cancelled.")
            return 0
        target = args.target
    else:
        args = parse_args(raw_args)
        target = current_platform()
    if not interactive and args.list:
        print(f"Detected target: {target} ({normalized_architecture()})")
        print("Builders: " + ", ".join(METHODS) + ", both")
        print("Formats: " + ", ".join(PLATFORM_FORMATS[target]))
        return 0

    try:
        if target == "windows" and normalized_architecture() != "x86_64":
            raise RuntimeError(
                "The Windows installer targets x64. Run the builder with 64-bit Python on x64 Windows."
            )
        formats = selected_formats(target, args.formats)
        methods = args.methods if interactive else (
            METHODS if args.method == "both" else (args.method,)
        )
        output = args.output.resolve()
        ensure_external_build_tools(target, methods, formats)
        ensure_python_build_packages(
            methods,
            interactive=interactive,
        )
        build_root = ROOT / "build" / "standalone"
        for method in methods:
            print(f"\n== Building with {method} for {target} ==")
            bundle = (
                build_pyinstaller(build_root, target)
                if method == "pyinstaller"
                else build_nuitka(build_root, target)
            )
            artifacts = create_artifacts(
                bundle,
                target,
                formats,
                output / target / method,
            )
            for artifact in artifacts:
                print(f"Created: {artifact}")
    except (EOFError, KeyboardInterrupt):
        print("\nBuild cancelled.")
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
