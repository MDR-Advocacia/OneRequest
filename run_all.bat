@echo off
REM --- MUDANÇA MAIS IMPORTANTE ---
REM Força o script a executar a partir da pasta onde ele está salvo
cd /d %~dp0

chcp 65001
echo Iniciando o Agendador Mestre de Robos...
echo.
echo Ativando o ambiente virtual...
REM Agora 'venv\...' será encontrado, pois estamos na pasta certa
call venv\Scripts\activate

echo.
echo Executando o script principal de automacao...
REM Agora 'run_robos.py' será encontrado
python run_robos.py

echo.
echo O processo foi finalizado.
pause