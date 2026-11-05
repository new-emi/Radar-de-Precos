@echo off
REM abrir_painel.bat - abre o Radar de Precos. Deixe esta janela aberta enquanto usar o painel.
REM Este arquivo fica em scripts\windows: sobe duas pastas para a raiz do projeto
cd /d "%~dp0..\.."
set PYTHONIOENCODING=utf-8
REM Fecha um painel antigo que tenha ficado aberto na porta 8501
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
echo.
echo  Abrindo o Radar de Precos...
echo  No celular (mesmo Wi-Fi), use o endereco "Network URL" que vai aparecer abaixo.
echo.
".venv\Scripts\python.exe" -m streamlit run painel.py
pause
