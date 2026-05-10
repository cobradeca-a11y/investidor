@echo off
chcp 65001 >nul
pushd "%~dp0"
title FIIA Intelligence - SISTEMA DE ELITE

echo [0/2] Limpando processos fantasmas...
taskkill /F /IM python.exe /T >nul 2>&1

echo Verificando partida... > ERRO_SISTEMA.txt
echo ==================================================
echo         FIIA INTELLIGENCE - MODO DIAGNOSTICO
echo ==================================================

:: Tenta rodar o servidor
echo [!] Ligando o motor...
.\venv\Scripts\python.exe app.py

if %ERRORLEVEL% NEQ 0 (
    echo [ALERTA] O motor falhou. Verifique o arquivo ERRO_SISTEMA.txt
)

echo.
pause
popd
