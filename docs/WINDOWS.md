# Running VDODesk on Windows 10 or 11

VDODesk retains its local browser/Python/FFmpeg architecture on Windows. It listens only on `127.0.0.1`; imported media and exports remain inside the extracted `projects` folder.

## Quick installation

1. Extract the entire ZIP to a writable folder such as `C:\VDODesk`. Do not run it from inside the ZIP preview.
2. Double-click `SETUP_WINDOWS.bat`. Approve the Windows Package Manager prompts for Python 3.12 and FFmpeg.
3. Close the setup window after installation so Windows refreshes `PATH`.
4. Double-click `START_WINDOWS.bat`.
5. Keep the terminal window open. The editor opens at <http://127.0.0.1:8765> in the default browser.

`START_WINDOWS.bat` prefers the project's `.venv`, then the Windows `py` launcher, then `python.exe`. It verifies Python 3.10+, `ffmpeg.exe`, and `ffprobe.exe` before starting and displays a useful error instead of closing silently.

## Manual prerequisite installation

If Windows Package Manager is unavailable, install Python from <https://www.python.org/downloads/windows/> and enable **Add python.exe to PATH**. Install an FFmpeg Windows build linked from <https://ffmpeg.org/download.html> and ensure its `bin` directory is on the user or system `PATH`. Open a new Command Prompt and confirm:

```bat
python --version
ffmpeg -version
ffprobe -version
```

Python 3.10 or newer is required. No Node.js, database, compiler, or C++ runtime is required.

## Optional advanced tracking

Double-click `INSTALL_ADVANCED_WINDOWS.bat` to create `.venv` and install OpenCV. Subject detection, sampled tracking, and segmentation masks use OpenCV when present. The editor, manual tracking, audio tools, and all export features work without this optional step.

## Usage and troubleshooting

- Windows Firewall may ask about Python. VDODesk binds only to the local computer (`127.0.0.1`); public network access is not required.
- If port 8765 is already in use, open Command Prompt in the VDODesk folder and run `START_WINDOWS.bat --port 8877`.
- If the browser does not open automatically, visit <http://127.0.0.1:8765> manually.
- If FFmpeg was just installed but is still reported missing, close every Command Prompt and restart `START_WINDOWS.bat` so the updated `PATH` is loaded.
- Keep the terminal open while editing. Press `Ctrl+C` once to stop the server cleanly.
- Projects, imported media, proxies, and exports are stored below `projects\`.
