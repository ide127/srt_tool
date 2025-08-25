# GEMINI.md

## Project Overview

This project is a GUI application for extracting and translating subtitles from CapCut projects. The application is built using Python with the `ttkbootstrap` library for the user interface.

The core functionality is divided into two main parts:

1.  **CapCut Subtitle Extractor:** This part of the application, found in `capcut_srt_extractor.py`, provides a graphical interface for users to select their CapCut projects folder. It then parses the `draft_info.json` files within each project to extract subtitle information and generate `.srt` files.

2.  **SRT Translator:** The `srt_tool_app/core.py` module contains the logic for translating the extracted SRT files. It works by:
    *   Splitting the SRT file into separate files for timestamps and text.
    *   Using the Gemini CLI (`gemini`) to translate the text file into Korean, guided by a detailed set of instructions in `prompt.txt`.
    *   Merging the translated text with the original timestamps to create a new, translated SRT file.

The application includes robust error handling, including retries with different models and validation of the translated output.

## Building and Running

The application can be run directly from the source code or built into a standalone executable using `PyInstaller`.

### Running from Source

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: A `requirements.txt` file does not exist, but based on `pyproject.toml` the dependencies are `ttkbootstrap`. A requirements file should be created for easier setup.)*

2.  **Run the application:**
    ```bash
    python main.py
    ```

### Building the Executable

The file `BUILD_INSTRUCTIONS.md` provides detailed steps for building the application into a standalone executable for Windows and macOS using `PyInstaller`. The general process is as follows:

1.  **Install PyInstaller and dependencies:**
    ```bash
    pip install pyinstaller ttkbootstrap
    ```

2.  **Run the PyInstaller command:**
    *   **For Windows:**
        ```bash
        pyinstaller --name "SRT_Tool" \
                    --onefile \
                    --windowed \
                    --add-data "prompt.txt:." \
                    --icon="icon.ico"
                    srt_tool.py
        ```
    *   **For macOS:**
        ```bash
        pyinstaller --name "SRT_Tool" \
                    --onefile \
                    --windowed \
                    --add-data "prompt.txt:." \
                    --icon="icon.icns" \
                    --osx-bundle-identifier "com.yourname.srttool" \
                    srt_tool.py
        ```

## Development Conventions

*   **UI:** The application uses `tkinter` and `ttkbootstrap` for its graphical user interface.
*   **Translation:** The core translation functionality relies on the Gemini CLI. The prompt used for translation is located in `prompt.txt` and is highly specific to the task of translating drama subtitles.
*   **Language:** The UI and comments in the code are a mix of English and Korean. The translation prompt is in Korean.
*   **File Structure:**
    *   `main.py`: The main entry point of the application.
    *   `capcut_srt_extractor.py`: Contains the logic for extracting subtitles from CapCut projects.
    *   `srt_tool_app/`: This directory contains the core logic for the SRT tool.
        *   `core.py`: Handles splitting, translating, and merging SRT files.
        *   `gui.py`: (Inferred) Contains the main application GUI class `SrtToolApp`.
        *   `utils.py`: (Inferred) Contains utility functions for parsing and validating data.
    *   `prompt.txt`: The prompt used for the Gemini translation model.
    *   `BUILD_INSTRUCTIONS.md`: Instructions for building the executable.
    *   `pyproject.toml`: Defines project dependencies.
