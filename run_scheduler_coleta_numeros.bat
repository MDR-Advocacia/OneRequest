@echo off
chcp 65001
echo Iniciando Agendador do ROBO 1 (Coletor de Numeros)...
echo Esta janela deve permanecer aberta.

call venv\Scripts\activate
python scheduler_coleta_numeros.py
pause