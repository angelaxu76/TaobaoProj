@echo off
chcp 65001 >nul
set PYTHONUTF8=1

set "ROOT=D:\Projects\VS-TaobaoProj\TaobaoProj"
cd /d "%ROOT%"

python ops/run_pipeline.py ecco
pause
