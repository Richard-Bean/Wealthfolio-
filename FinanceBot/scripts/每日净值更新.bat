@echo off
chcp 65001 >nul
set "NAV_CACHE=%~dp0..\data\processed\market_data\净值缓存.json"
"%LocalAppData%\Programs\Python\Python312\python.exe" "%~dp0update_nav_cache.py" --output "%NAV_CACHE%" %*
if errorlevel 1 (
  echo.
  echo ===== 净值更新失败，保留原有本地缓存 =====
) else (
  echo.
  echo ===== 净值缓存更新成功：%NAV_CACHE% =====
)
pause