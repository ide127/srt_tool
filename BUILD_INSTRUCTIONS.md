# How to Build and Run the SRT Tool

This guide provides instructions for setting up the environment and building a standalone executable for the SRT Tool.

**IMPORTANT:** This application uses OpenAI's Whisper for audio transcription. For optimal performance, GPU acceleration is highly recommended. The following instructions include steps for setting up an AMD GPU on a WSL/Ubuntu environment.

## 1. Install Dependencies

Open your WSL/Ubuntu terminal.

### 1.1 Install System Dependencies
First, update your package lists and install `ffmpeg`, which is required by Whisper to process audio from video files.
```bash
sudo apt update && sudo apt upgrade
sudo apt install ffmpeg
```

### 1.2 Install Python Dependencies with `pip`
It is recommended to use a virtual environment. Once activated, install the required Python libraries:
```bash
pip install openai-whisper ttkbootstrap torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.7
pip install pyinstaller srt
```
**Note on `srt`:** This library is used for robust parsing of SRT files.
**Note on PyTorch:** The `--index-url` for PyTorch is crucial for installing a version compatible with AMD's ROCm. Ensure your ROCm version matches (e.g., `rocm5.7`).

## 2. Setting up AMD GPU Acceleration (ROCm on WSL)
This is a complex process. Follow these steps carefully.

### 2.1 Install AMD GPU Drivers on Windows
Ensure you have the latest official AMD Adrenalin drivers installed on your Windows 11 host.

### 2.2 Install ROCm in WSL
Follow the official AMD guide for installing the ROCm toolchain on Linux. A typical installation command would be:
```bash
sudo apt install rocm-dkms
```
This can be a lengthy and complex process. Refer to AMD's official documentation for the most up-to-date instructions for your specific GPU and Ubuntu version.

### 2.3 Add User to Render/Video Groups
Your WSL user needs permission to access the GPU hardware.
```bash
sudo usermod -a -G render,video $USER
```
You will need to close and reopen your WSL terminal for this to take effect.

### 2.4 Verify Installation
You can verify that PyTorch can see your GPU by running the following in Python:
```python
import torch
print(torch.cuda.is_available())
# Should print True
print(torch.cuda.get_device_name(0))
# Should print your AMD GPU name
```

## 3. How to Run the Application
Once all dependencies are installed, you can run the application directly from the source code:
```bash
python srt_tool.py
```

## 4. How to Build an Executable (Optional)
Navigate to the project's root directory in your terminal.

```bash
pyinstaller --name "SRT_Sync_Tool" \
            --onefile \
            --windowed \
            --add-data "config.py:." \
            --add-data "prompts.py:." \
            srt_tool.py
```
This creates a single `.exe` file in the `dist` folder. Note that for GPU acceleration to work, the target machine must also have the correct AMD drivers and ROCm environment installed. Building a truly portable GPU-accelerated application is highly complex.
