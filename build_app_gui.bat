
@echo off
setlocal

call "%ProgramFiles%\Microsoft Visual Studio\18\Community\Common7\Tools\VsDevCmd.bat" -arch=x64

if errorlevel 1 (
    echo Failed to initialize Visual Studio.
    pause
    exit /b 1
)

set "PATH=%PATH%;C:\Program Files (x86)\Inno Setup 6"

cd /d "%~dp0"

python build_gui.py

pause
