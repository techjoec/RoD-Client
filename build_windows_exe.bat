@echo off
setlocal
REM Build Windows executable using PyInstaller (onefile, windowed)
REM Prereqs: Python 3.9+ and pip install pyinstaller

where py >NUL 2>&1 && set "PY=py" || set "PY=python"

%PY% -m pip install --upgrade pyinstaller || goto :error
%PY% -m PyInstaller --clean RealmsClient.spec || goto :error
echo.
echo Build complete. Find the exe in dist\RealmsClient.exe
endlocal
goto :eof

:error
echo Build failed. Ensure Python and PyInstaller are installed.
exit /b 1
