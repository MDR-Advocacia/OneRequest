@echo off
echo Iniciando o servidor do painel OneRequest...

REM Ativa o ambiente virtual. Ajuste o caminho se o seu venv estiver em outro lugar.
call RPA\venv\Scripts\activate

REM Inicia o servidor Waitress para a sua aplicação Flask
REM O app:app significa "do arquivo app.py, use a variável app"
waitress-serve --host=0.0.0.0 --port=5001 server:app

pause