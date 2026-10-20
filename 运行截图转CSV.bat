@echo off
setlocal
title Wealthfolio Screenshot to CSV

set "PROJECT_ROOT=%~dp0"
set "SCRIPT=%PROJECT_ROOT%FinanceBot\scripts\run_screenshot_pipeline.py"

echo ============================================
echo   Wealthfolio Screenshot to CSV
echo ============================================
echo.
echo Input folder:
echo   "%PROJECT_ROOT%FinanceBot\data\raw\alipay"
echo.
echo Processing screenshots, please wait...
echo.

where py >nul 2>&1
if not errorlevel 1 goto :run_with_py

where python >nul 2>&1
if not errorlevel 1 goto :run_with_python

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" goto :run_with_fixed_python

echo [ERROR] Python 3 was not found.
echo Please install Python 3, then double-click this file again.
echo.
pause
exit /b 1

:run_with_py
py -3 "%SCRIPT%"
goto :check_result

:run_with_python
python "%SCRIPT%"
goto :check_result

:run_with_fixed_python
"%LocalAppData%\Programs\Python\Python312\python.exe" "%SCRIPT%"
goto :check_result

:check_result
if errorlevel 1 goto :error

echo.
echo ============================================
echo   Completed
echo ============================================
echo.
echo CSV:
echo   "%PROJECT_ROOT%FinanceBot\data\export\wealthfolio_import_auto.csv"
echo.
echo Comparison report:
echo   "%PROJECT_ROOT%FinanceBot\data\processed\reconciliation\alipay\snapshot_comparison.json"
echo.
echo Review the report before importing the CSV into Wealthfolio.
echo.
pause
exit /b 0

:error
echo.
echo ============================================
echo   Failed
echo ============================================
echo.
echo Please review the error messages above.
echo The previous successful output was not overwritten.
echo.
pause
exit /b 1
