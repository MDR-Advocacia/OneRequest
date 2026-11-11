#!/bin/sh
# Lança o worker HTTP (trigger manual) em background e o agendador em foreground.
# Se o agendador morrer, o container reinicia (restart: unless-stopped).
python rpa_worker.py &
exec python run_robos.py
