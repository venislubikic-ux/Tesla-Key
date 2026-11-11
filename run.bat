@echo off
REM Запуск из исходников (создаёт виртуальное окружение при первом запуске)
if not exist .venv (
    py -3 -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)
start "" pythonw main.py
