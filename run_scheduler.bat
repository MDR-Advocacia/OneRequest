@echo off
echo Iniciando o Agendador dos Robos OneRequest...
echo.
echo Esta janela deve permanecer aberta para que o agendamento funcione.
echo Pressione CTRL+C para parar.
echo.

REM Ativa o ambiente virtual
call RPA\venv\Scripts\activate

REM Inicia o script de agendamento
python scheduler.py

pause