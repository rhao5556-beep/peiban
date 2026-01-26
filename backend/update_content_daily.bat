@echo off
REM 每日内容更新脚本
REM 用法: 双击运行或在命令行执行

echo ========================================
echo 每日内容更新
echo ========================================
echo.

echo 正在抓取最新RSS内容...
python seed_real_rss_content.py

echo.
echo ========================================
echo 更新完成！
echo ========================================
echo.
echo 提示：你可以将此脚本添加到Windows任务计划程序
echo 实现每天自动运行
echo.
pause
