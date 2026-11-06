@echo off
rem Daily ClimaGuard pipeline: live weather -> risk for 7/14 days -> alerts -> outbox.
rem Run by the Windows scheduled task "ClimaGuard daily run"; safe to run by hand (a re-run replaces today's run).
cd /d "%~dp0"
if not exist logs mkdir logs
echo ==== %date% %time% >> logs\run-live.log
rem Full path so the task does not depend on PATH; update it if Python is reinstalled.
"C:\Users\DARWIN S\AppData\Local\Programs\Python\Python310\python.exe" -m climaguard.cli run-live >> logs\run-live.log 2>&1
echo exit code %errorlevel% >> logs\run-live.log
exit /b %errorlevel%
