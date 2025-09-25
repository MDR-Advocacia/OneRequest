@echo off
echo [INFO] Abrindo Google Chrome com depuracao remota...

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
--remote-debugging-port=9222 ^
--user-data-dir="C:\temp\chrome-perfil"

echo [OK] Chrome aberto.
rem Faça login manual no site do BB Jurídico.
pause