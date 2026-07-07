$projectDir = "C:\Users\User\Documents\git\projects\reading_journey"
$python = Join-Path $projectDir "venv\Scripts\python.exe"
$logFile = Join-Path $projectDir "app_run.log"
$errFile = Join-Path $projectDir "app_run_err.log"

Start-Process -FilePath $python `
    -ArgumentList "app.py" `
    -WorkingDirectory $projectDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError $errFile
