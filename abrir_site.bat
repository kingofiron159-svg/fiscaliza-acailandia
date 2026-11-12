@echo off
rem Abre o Fiscaliza no navegador. Deixe esta janela aberta enquanto usa o site.
cd /d "%~dp0"
start "" http://localhost:8765
echo Site em http://localhost:8765  -  feche esta janela para desligar.
python -m http.server 8765 --directory site
pause
