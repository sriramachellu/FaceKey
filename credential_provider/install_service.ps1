<#
.SYNOPSIS
    Set up FaceKey service to auto-start at user login.
.PARAMETER Remove
    Remove the auto-start entry.
#>
param(
    [switch]$Remove
)

$TaskName = "FaceKey Service"

if ($Remove) {
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        Write-Host "Removed FaceKey auto-start task." -ForegroundColor Green
    } catch {
        Write-Host "Task not found or already removed." -ForegroundColor Yellow
    }
    return
}

# Find Python in the facekey conda env
$Python = "C:\Users\$env:USERNAME\miniforge3\envs\facekey\python.exe"
if (-not (Test-Path $Python)) {
    $Python = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $Python -or -not (Test-Path $Python)) {
    Write-Host "ERROR: Cannot find Python. Set the path manually." -ForegroundColor Red
    exit 1
}

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "-m facekey service" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "FaceKey face authentication service for Windows login" `
    -Force | Out-Null

Write-Host "FaceKey service will auto-start at login." -ForegroundColor Green
Write-Host "Task name: '$TaskName'" -ForegroundColor Cyan
