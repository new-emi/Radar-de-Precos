@echo off
REM abrir_para_mae.bat - abre o painel E cria um link publico (Cloudflare) para acessar de qualquer lugar.
REM Precisa do cloudflared instalado:  winget install --id Cloudflare.cloudflared
REM Deixe esta janela aberta enquanto sua mae estiver usando.
REM Este arquivo fica em scripts\windows: sobe duas pastas para a raiz do projeto
cd /d "%~dp0..\.."
set PYTHONIOENCODING=utf-8
REM Fecha um painel antigo que tenha ficado aberto (senao o tunel apontaria para a versao velha)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
start "Radar de Precos - painel" /min ".venv\Scripts\python.exe" -m streamlit run painel.py --server.headless true --server.port 8501
timeout /t 5 /nobreak >nul
echo.
echo  ================================================================
echo   O link para sua mae e o endereco https://....trycloudflare.com
echo   que vai aparecer abaixo (no meio do texto, num quadro).
echo   O link muda toda vez que voce abrir este arquivo.
echo   Ao fechar esta janela, o link para de funcionar.
echo  ================================================================
echo.
cloudflared tunnel --url http://localhost:8501
pause
