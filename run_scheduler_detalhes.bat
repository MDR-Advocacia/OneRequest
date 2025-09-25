@echo off
chcp 65001
echo Iniciando Agendador do ROBO 2 (Detalhador de Solicitacoes)...
echo Esta janela deve permanecer aberta.

call venv\Scripts\activate
python scheduler_detalhes.py
pause