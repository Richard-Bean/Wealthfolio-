@echo off
chcp 65001 >nul
"%LocalAppData%\Programs\Python\Python312\python.exe" "%~dp0scripts\run.py"
if errorlevel 1 (
  echo.
  echo ===== 运行出错，请查看上方错误信息 =====
) else (
  echo.
  echo ===== 成功！CSV 已生成到 data\processed\alipay 目录 =====
)
pause
