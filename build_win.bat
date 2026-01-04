@echo off
setlocal

echo ==========================================
echo    AIrewrite Windows Build Script
echo ==========================================

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

:: Install requirements
echo [1/3] Installing dependencies...
pip install -r requirements_win.txt

:: Build the app
echo [2/3] Building EXE with PyInstaller...
pyinstaller --clean --noconfirm AIrewrite_win.spec

echo [3/3] Done! 
echo.
echo The application has been built in the "dist/AIrewrite" folder.
echo You can run it by opening "dist/AIrewrite/AIrewrite.exe".
echo.
pause
