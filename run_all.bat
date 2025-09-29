@echo off
chcp 65001
echo Iniciando o Agendador Mestre de Robos...
echo.
echo Ativando o ambiente virtual...
call venv\Scripts\activate

echo.
echo Executando o script principal de automacao...
python run_robos.py

echo.
echo O processo foi finalizado.
pause