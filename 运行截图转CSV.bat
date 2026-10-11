@echo off

chcp 65001 >nul

set "PROJECT_ROOT=%~dp0"

set "INPUT=%PROJECT_ROOT%\FinanceBot\data\processed\alipay\snapshot_input.auto.json"

if "%~1"=="" (

  "%LocalAppData%\Programs\Python\Python312\python.exe" "%PROJECT_ROOT%\FinanceBot\scripts\ocr_to_snapshot.py"

) else (

  "%LocalAppData%\Programs\Python\Python312\python.exe" "%PROJECT_ROOT%\FinanceBot\scripts\ocr_to_snapshot.py" %*

)

if errorlevel 1 goto :error

"%LocalAppData%\Programs\Python\Python312\python.exe" "%PROJECT_ROOT%\FinanceBot\scripts\update_nav_cache.py" --input "%INPUT%"

if errorlevel 1 goto :error

"%LocalAppData%\Programs\Python\Python312\python.exe" "%PROJECT_ROOT%\FinanceBot\connectors\alipay\scripts\build_snapshot_import.py" --input "%INPUT%" --require-nav --output "%PROJECT_ROOT%\FinanceBot\data\processed\alipay\wealthfolio_import_auto.csv" --export "%PROJECT_ROOT%\FinanceBot\data\export\wealthfolio_import_auto.csv"

if errorlevel 1 goto :error

echo.

echo ===== 完成：请导入 FinanceBot\data\export\wealthfolio_import_auto.csv =====

pause

exit /b 0

:error

echo.

echo ===== 运行失败，请查看上方错误；未生成不完整 CSV =====

pause

exit /b 1

