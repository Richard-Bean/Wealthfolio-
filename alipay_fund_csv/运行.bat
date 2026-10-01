@echo off
cd /d "D:\my-code-project\Wealthfolio中国金融同步连接器架构设计\alipay_fund_csv"
"C:\Users\lenovo\AppData\Local\Programs\Python\Python312\python.exe" scripts/run.py
if errorlevel 1 (
  echo.
  echo ===== 运行出错，请截图此窗口发给助手 =====
) else (
  echo.
  echo ===== 成功！两份 CSV 已生成到 data\output 目录 =====
)
pause
