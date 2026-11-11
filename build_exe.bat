@echo off
REM Сборка TK.exe (один файл, без консоли). Запускать из папки проекта.
setlocal
if not exist .venv (
    py -3 -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip >nul
pip install -r requirements-build.txt || goto :error

pyinstaller --noconfirm --clean --onefile --windowed ^
    --name TK ^
    --icon assets\tk.ico ^
    --add-data "assets;assets" ^
    --hidden-import keyring.backends.Windows ^
    --collect-submodules keyring.backends ^
    main.py || goto :error

echo.
echo Готово: dist\TK.exe
exit /b 0
:error
echo Сборка не удалась.
exit /b 1
