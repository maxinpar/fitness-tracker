@echo off
:: Garmin daily sync runner - called by Windows Task Scheduler.
:: Appends output to a rolling log file.

cd /d "C:\Users\maxim\PycharmProjects\fitness-tracker"
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

:: Keep only the last 500 lines of the log so it cannot grow forever.
if exist garmin_sync.log (
    powershell -Command "Get-Content garmin_sync.log | Select-Object -Last 500 | Set-Content garmin_sync_tmp.log; Move-Item -Force garmin_sync_tmp.log garmin_sync.log"
)

echo. >> garmin_sync.log
echo ============================== >> garmin_sync.log
echo %DATE% %TIME% >> garmin_sync.log
echo ============================== >> garmin_sync.log

"C:\Users\maxim\PycharmProjects\fitness-tracker\.venv\Scripts\python.exe" garmin_sync.py --non-interactive >> garmin_sync.log 2>&1

echo Exit code: %ERRORLEVEL% >> garmin_sync.log
