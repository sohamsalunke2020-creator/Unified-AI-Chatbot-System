@echo off
REM Unified Chatbot System - Setup Script for Windows

echo.
echo ================================================
echo   Unified AI Chatbot System - Windows Setup
echo ================================================
echo.

REM Check Python version
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Install Python 3.8+ from https://www.python.org
    pause
    exit /b 1
)

echo [1/5] Python found
echo.

REM Create virtual environment
echo [2/5] Creating virtual environment...
if exist venv (
    echo Virtual environment already exists
) else (
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)
echo.

REM Activate virtual environment
echo [3/5] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo.

REM Install dependencies
echo [4/5] Installing dependencies (this may take a few minutes)...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo.

REM Download spacy models
echo [5/5] Downloading NLP models...
python -m spacy download en_core_web_sm --quiet
if errorlevel 1 (
    echo [WARNING] Failed to download spacy model, you may need to run:
    echo python -m spacy download en_core_web_sm
)
echo.

echo.
echo ================================================
echo   Setup Complete!
echo ================================================
echo.
echo Next steps:
echo.
echo 1. Configure API Keys:
echo    Edit .env file and add your API keys from:
echo    - Google AI Studio (https://ai.google.dev/)
echo.
echo 2. Run the Chatbot:
echo    Option A - Web Interface (Recommended):
echo       streamlit run ui/streamlit_app.py
echo.
echo    Option B - Command Line:
echo       python chatbot_main.py
echo.
echo 3. Read Documentation:
echo    - QUICKSTART.md - Quick start guide
echo    - README.md - Full documentation
echo    - CONFIG_GUIDE.md - Configuration reference
echo.
echo ================================================
echo.

REM Create batch files for easy launch
echo Creating launch scripts...

REM Web UI launcher
(
    echo @echo off
    echo title Unified Chatbot - Web Interface
    echo echo Launching Streamlit interface...
    echo streamlit run ui/streamlit_app.py
) > run_web_ui.bat

REM CLI launcher
(
    echo @echo off
    echo title Unified Chatbot - Command Line
    echo echo Launching command line interface...
    echo python chatbot_main.py
) > run_cli.bat

echo Launch scripts created:
echo - run_web_ui.bat (Web interface)
echo - run_cli.bat (Command line)
echo.

pause
