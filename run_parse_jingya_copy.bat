@echo off
chcp 65001 >nul
cd /d "d:\Projects\VS-TaobaoProj\TaobaoProj"
set "PYTHONPATH=d:\Projects\VS-TaobaoProj\TaobaoProj"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
python -m helper.excel.parse_jingya_copy_to_excel
echo.
echo ==== done, press any key to close ====
pause >nul
