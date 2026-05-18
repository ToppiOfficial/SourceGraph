@echo off
setlocal

echo Checking for Python 3.14...

:: Try using 'py -3.14' first (Python Launcher for Windows)
py -3.14 --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_EXE=py -3.14
) else (
    :: Fallback to 'python' and check version
    python --version 2>&1 | find "3.14" >nul
    if %errorlevel% equ 0 (
        set PYTHON_EXE=python
    ) else (
        echo [ERROR] Python 3.14 is required but not found.
        echo Please install Python 3.14 or ensure it is in your PATH.
        pause
        exit /b 1
    )
)

:: Check if venv exists
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment not found. Creating one...
    %PYTHON_EXE% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [INFO] Virtual environment created successfully.
    
    echo [INFO] Installing dependencies from requirements.txt...
    call .venv\Scripts\activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [WARNING] Some dependencies failed to install.
    )
) else (
    echo [INFO] Virtual environment found. Activating...
    call .venv\Scripts\activate
)

:: Start the application
echo [INFO] Starting SourceGraph (main.py)...
python main.py

if %errorlevel% neq 0 (
    echo [INFO] Application exited with error code %errorlevel%.
    pause
)

endlocal
