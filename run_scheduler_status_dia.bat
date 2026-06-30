@echo off
chcp 65001
setlocal
set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%venv\Scripts\python.exe"
cd /d "%PROJECT_DIR%"
set "PYTHONUTF8=1"
echo Iniciando agendador 'Status do Dia'...
"%PYTHON_EXE%" "%PROJECT_DIR%scheduler_status_dia.py"
