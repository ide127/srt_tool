# How to Build and Run the SRT Tool

This guide provides instructions for setting up the environment and building a standalone executable for the SRT Tool.

## 1. Install Dependencies

It is recommended to use a virtual environment. Once activated, install the required Python libraries:

```bash
pip install ttkbootstrap srt
```

## 2. How to Run the Application
Once all dependencies are installed, you can run the application directly from the source code:
```bash
python main.py
```

## 3. How to Build an Executable (Optional)
Navigate to the project's root directory in your terminal.

```bash
pyinstaller --name "SRT_Tool" \
            --onefile \
            --windowed \
            --add-data "srt_tool_app/config.py:srt_tool_app" \
            --add-data "prompts:prompts" \
            main.py
```
This creates a single `.exe` file (on Windows) or a `.app` bundle (on macOS) in the `dist` folder.
