@echo off
chcp 65001 >nul
set "PROJECT_ROOT=%~dp0"
"%LocalAppData%\Programs\Python\Python312\python.exe" "%PROJECT_ROOT%FinanceBot\scripts\run_screenshot_pipeline.py"
if errorlevel 1 goto :error
echo.
echo ===== 完成：截图已分类并生成 CSV =====
pause
exit /b 0

:error
echo.
echo ===== 运行失败，请查看上方错误 =====
pause
exit /b 1