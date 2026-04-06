@echo off
setlocal
chcp 65001 >nul
title DI 규정 자동 확인 시스템 실행기

:: ── 강제 재설치 옵션: run_app.bat --reinstall 으로 실행하면 패키지 재설치 ──
set REINSTALL=0
if "%1"=="--reinstall" set REINSTALL=1

echo [1/3] 파이썬 환경을 확인 중입니다...
python --version
if %errorlevel% neq 0 (
    echo [오류] 파이썬이 설치되어 있지 않거나 PATH에 추가되지 않았습니다.
    echo 파이썬(3.9 이상)을 먼저 설치해 주세요.
    pause
    exit /b
)

:: ── 이미 streamlit이 설치되어 있으면 pip install 전체를 건너뜀 ──
echo [2/3] 라이브러리 설치 여부를 확인합니다...
python -m streamlit --version >nul 2>&1
if %errorlevel% equ 0 (
    if %REINSTALL%==0 (
        echo [스킵] streamlit이 이미 설치되어 있습니다. 설치 단계를 건너뜁니다.
        echo       (패키지를 다시 설치하려면 cmd에서 run_app.bat --reinstall 를 실행하세요.)
        goto START_APP
    )
)

echo 필요한 라이브러리를 설치합니다. 최초 실행 시 시간이 소요됩니다...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [오류] 라이브러리 설치에 실패했습니다. 위 오류 메시지를 확인하세요.
    pause
    exit /b
)

:START_APP
echo [3/3] 시스템을 시작합니다...
echo 잠시 후 웹 브라우저가 열리면 대상을 검색하실 수 있습니다.
python -m streamlit run app.py

pause
