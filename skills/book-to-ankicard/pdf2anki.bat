@echo off
chcp 65001 >nul
setlocal
set PYTHONUTF8=1
set HERE=%~dp0
if "%~1"=="" (
  echo 用法：把 PDF 拖到本文件上；或在命令行运行  pdf2anki.bat 教材.pdf 科目名 [--only 1,2]
  pause
  exit /b 1
)
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
set VENV=%USERPROFILE%\.pdf2anki-venv
if not exist "%VENV%\Scripts\python.exe" (
  echo 第一次运行：安装依赖（约 1-2 分钟）...
  %PY% -m venv "%VENV%"
  if errorlevel 1 (
    echo 没找到 Python。请先安装 Python 3.9 以上：https://www.python.org/downloads/ （安装时勾选 Add Python to PATH）
    pause
    exit /b 1
  )
  "%VENV%\Scripts\python.exe" -m pip install -q pymupdf opencv-python-headless numpy
)
"%VENV%\Scripts\python.exe" "%HERE%pdf2anki.py" %*
echo.
pause
