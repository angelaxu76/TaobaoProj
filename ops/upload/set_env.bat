@echo off
:: ============================================================
:: set_env.bat — 在本机设置 UiPath 环境变量
:: 每台机器按实际路径修改下面 ROBOT_EXE 的值，然后双击运行即可
:: 设置后重启终端 / VSCode 生效
:: ============================================================

set ROBOT_EXE=C:\Users\maddingxu\AppData\Local\Programs\UiPathPlatform\Studio\26.0.191-cloud.22694\UiRobot.exe

:: 写入用户级环境变量（不需要管理员权限）
setx UIPATH_ROBOT_EXE "%ROBOT_EXE%"

if %errorlevel% == 0 (
    echo.
    echo [OK] 环境变量已设置：
    echo      UIPATH_ROBOT_EXE = %ROBOT_EXE%
    echo.
    echo 请重启终端或 VSCode 后生效。
) else (
    echo.
    echo [ERROR] 设置失败，请检查路径是否正确。
)

pause
