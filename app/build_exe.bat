@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ not found. Install it and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist .venv\ready.txt (
  echo Creating environment...
  python -m venv .venv
  if errorlevel 1 goto fail
  .venv\Scripts\python -m pip install -r requirements.txt
  if errorlevel 1 goto fail
  echo ok> .venv\ready.txt
)
.venv\Scripts\python -m pip install pyinstaller
if errorlevel 1 goto fail
.venv\Scripts\python -m PyInstaller --noconfirm --windowed --name SpectrumPro --icon ramanproc\assets\spectrumpro.ico --add-data "ramanproc\assets;ramanproc\assets" run_gui.py
if errorlevel 1 goto fail
echo.
echo Done: dist\SpectrumPro\SpectrumPro.exe  (copy the whole dist\SpectrumPro folder)
pause
exit /b 0
:fail
echo Failed. See messages above.
pause
exit /b 1
