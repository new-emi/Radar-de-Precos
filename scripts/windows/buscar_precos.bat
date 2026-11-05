@echo off
REM buscar_precos.bat - roda o robo uma vez e guarda o registro em busca_automatica.log
REM E este arquivo que o Agendador de Tarefas do Windows chama todo dia.
REM Este arquivo fica em scripts\windows: sobe duas pastas para a raiz do projeto
cd /d "%~dp0..\.."
set PYTHONIOENCODING=utf-8
echo. >> busca_automatica.log
echo ===== %date% %time% ===== >> busca_automatica.log
".venv\Scripts\python.exe" robo.py >> busca_automatica.log 2>&1
