@echo off
rem Build the FSOC-PAT standalone application on Windows.
rem Run from the repository root:  packaging\build.bat
rem Requires: python 3.10+ on PATH.

python -m venv .venv-build || goto :error
call .venv-build\Scripts\activate.bat
pip install -e . pyinstaller PySide6 pyqtgraph || goto :error
pyinstaller --noconfirm --clean packaging\fsoc-pat.spec || goto :error
echo.
echo Build complete: dist\fsoc-pat\fsoc-pat.exe
echo Ship the whole dist\fsoc-pat folder (zip it for submission).
goto :eof
:error
echo BUILD FAILED
exit /b 1
