@echo off
SETLOCAL

REM Define task parameters
SET "TASK_NAME=AlgoTraderDailyRun"
SET "EXE_NAME=algotrader.exe"

REM Get the current directory path (CRITICAL for portability)
SET "DEPLOY_PATH=%~dp0"

echo --- Using current directory for deployment: %DEPLOY_PATH% ---
echo --- Creating Scheduled Task to run under your user account for VISIBILITY ---

REM The entire task creation is run inside PowerShell on a single line.
REM FIX: LogonType changed from 'InteractiveToken' to the correct 'Interactive'
powershell.exe -NoProfile -Command "$action = New-ScheduledTaskAction -Execute '%DEPLOY_PATH%%EXE_NAME%' -WorkingDirectory '%DEPLOY_PATH%'; $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday, Sunday, Monday, Tuesday, Wednesday -At 08:35; $principal = New-ScheduledTaskPrincipal -UserId \"$env:USERNAME\" -LogonType Interactive -RunLevel Highest; $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances Parallel; Register-ScheduledTask -TaskName '%TASK_NAME%' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force"

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo FATAL ERROR: PowerShell script failed to create the scheduled task. Error code: %ERRORLEVEL%
    echo Ensure you are running this batch file \"As Administrator\".
    pause
    GOTO :EOF
)

echo.
echo SUCCESS: The task \"%TASK_NAME%\" has been created successfully.
echo It is configured to run visibly on your logged-in desktop.
pause

ENDLOCAL