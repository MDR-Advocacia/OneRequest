@echo off
echo [🌐] Abrindo Google Chrome com depuração remota...

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
--remote-debugging-port=9222 ^
--user-data-dir="C:\temp\chrome-perfil"

echo [✔] Chrome aberto. Faça login manual no site do BB Jurídico.
pause
