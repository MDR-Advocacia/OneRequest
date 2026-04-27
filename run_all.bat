@echo off
chcp 65001
setlocal

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%venv\Scripts\python.exe"
set "MAIN_SCRIPT=%PROJECT_DIR%run_robos.py"

cd /d "%PROJECT_DIR%"

echo =========================================================
echo   OneRequest - Agendador Mestre de Robos
echo =========================================================
echo.

if not exist "%PYTHON_EXE%" (
    echo [ERRO] Ambiente virtual nao encontrado em:
    echo        %PYTHON_EXE%
    echo.
    echo Crie ou ajuste o venv antes de executar este script.
    exit /b 1
)

if not exist "%MAIN_SCRIPT%" (
    echo [ERRO] Script principal nao encontrado em:
    echo        %MAIN_SCRIPT%
    exit /b 1
)

echo [INFO] Projeto: %PROJECT_DIR%
echo [INFO] Python:  %PYTHON_EXE%
echo [INFO] Script:  %MAIN_SCRIPT%
echo.
echo [INFO] Iniciando automacao...
echo.

"%PYTHON_EXE%" "%MAIN_SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [OK] Processo finalizado com sucesso.
) else (
    echo [ERRO] Processo finalizado com codigo %EXIT_CODE%.
)

exit /b %EXIT_CODE%
