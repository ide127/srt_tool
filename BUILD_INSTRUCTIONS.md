# How to Build the SRT Tool Executable

This guide provides instructions on how to package the SRT Tool into a standalone executable for Windows and macOS using `PyInstaller`.

## Prerequisites

-   Python 3.x installed on your system.
-   `pip` (the Python package installer) available in your command line or terminal.

## 1. Install PyInstaller

Open your terminal (Command Prompt on Windows, Terminal on macOS) and run the following command to install the required libraries:

```bash
pip install pyinstaller ttkbootstrap
```

## 2. Prepare for Build

Make sure the following files are in the same directory:
-   `srt_tool.py`
-   `prompt.txt`

Optionally, you can add an application icon file:
-   For Windows: an `.ico` file (e.g., `icon.ico`)
-   For macOS: an `.icns` file (e.g., `icon.icns`)

## 3. Build the Executable

Navigate to the directory containing the script in your terminal.

### For Windows

Run the following command:

```bash
pyinstaller --name "SRT_Tool" ^
            --onefile ^
            --windowed ^
            --add-data "prompt.txt:." ^
            --icon="icon.ico" ^
            srt_tool.py
```

-   `--name`: Sets the name of your final executable.
-   `--onefile`: Bundles everything into a single `.exe` file.
-   `--windowed`: Prevents the black console window from appearing when you run the app.
-   `--add-data "prompt.txt:."`: Ensures `prompt.txt` is included in the package. The `:.` part means it will be placed in the root of the package, where the script can find it.
-   `--icon`: (Optional) Adds your custom icon to the executable.

### For macOS

Run the following command:

```bash
pyinstaller --name "SRT_Tool" \
            --onefile \
            --windowed \
            --add-data "prompt.txt:." \
            --icon="icon.icns" \
            --osx-bundle-identifier "com.yourname.srttool" \
            srt_tool.py
```

-   The flags are similar to Windows.
-   `--osx-bundle-identifier`: (Optional but recommended) Sets a unique bundle identifier for the application on macOS.

## 4. Find Your Application

After the build process completes, you will find a `dist` folder. Inside this folder, you will find:
-   On Windows: `SRT_Tool.exe`
-   On macOS: `SRT_Tool.app`

This is your standalone application that can be shared and run on other computers without needing Python installed.
