#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Register or unregister the FaceKey Credential Provider.
.PARAMETER Unregister
    Remove the credential provider registration.
.EXAMPLE
    .\register.ps1                  # Register
    .\register.ps1 -Unregister      # Unregister
#>
param(
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

$CLSID = "{A5B3C2D1-4E5F-6A7B-8C9D-0E1F2A3B4C5D}"
$DllName = "FaceKeyProvider.dll"
$ProviderName = "FaceKey Face Unlock"

# Find the DLL
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DllPath = Join-Path $ScriptDir "build\bin\Release\$DllName"
if (-not (Test-Path $DllPath)) {
    $DllPath = Join-Path $ScriptDir "build\bin\$DllName"
}
if (-not (Test-Path $DllPath)) {
    $DllPath = Join-Path $ScriptDir "build\bin\Debug\$DllName"
}

$SystemDll = Join-Path $env:SystemRoot "System32\$DllName"

if ($Unregister) {
    Write-Host "Unregistering FaceKey Credential Provider..." -ForegroundColor Yellow

    # Remove credential provider registration
    $cpKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$CLSID"
    if (Test-Path $cpKey) {
        Remove-Item -Path $cpKey -Recurse -Force
        Write-Host "  Removed credential provider registry key"
    }

    # Remove CLSID registration
    $clsidKey = "HKLM:\SOFTWARE\Classes\CLSID\$CLSID"
    if (Test-Path $clsidKey) {
        Remove-Item -Path $clsidKey -Recurse -Force
        Write-Host "  Removed CLSID registry key"
    }

    # Remove DLL from System32
    if (Test-Path $SystemDll) {
        Remove-Item -Path $SystemDll -Force
        Write-Host "  Removed $SystemDll"
    }

    Write-Host "FaceKey Credential Provider unregistered." -ForegroundColor Green
    Write-Host "Changes take effect at next logon." -ForegroundColor Cyan
}
else {
    if (-not (Test-Path $DllPath)) {
        Write-Host "ERROR: Cannot find $DllName" -ForegroundColor Red
        Write-Host "Build the project first:" -ForegroundColor Yellow
        Write-Host "  cd credential_provider"
        Write-Host "  cmake -B build -A x64"
        Write-Host "  cmake --build build --config Release"
        exit 1
    }

    Write-Host "Registering FaceKey Credential Provider..." -ForegroundColor Yellow

    # Copy DLL to System32
    Copy-Item -Path $DllPath -Destination $SystemDll -Force
    Write-Host "  Copied DLL to $SystemDll"

    # Register CLSID
    $clsidKey = "HKLM:\SOFTWARE\Classes\CLSID\$CLSID"
    New-Item -Path $clsidKey -Force | Out-Null
    Set-ItemProperty -Path $clsidKey -Name "(Default)" -Value $ProviderName

    $inprocKey = "$clsidKey\InprocServer32"
    New-Item -Path $inprocKey -Force | Out-Null
    Set-ItemProperty -Path $inprocKey -Name "(Default)" -Value $DllName
    Set-ItemProperty -Path $inprocKey -Name "ThreadingModel" -Value "Apartment"
    Write-Host "  Registered CLSID"

    # Register as credential provider
    $cpKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$CLSID"
    New-Item -Path $cpKey -Force | Out-Null
    Set-ItemProperty -Path $cpKey -Name "(Default)" -Value $ProviderName
    Write-Host "  Registered credential provider"

    Write-Host ""
    Write-Host "FaceKey Credential Provider registered!" -ForegroundColor Green
    Write-Host "The FaceKey tile will appear at next logon/lock." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "IMPORTANT: Make sure the FaceKey service is running:" -ForegroundColor Yellow
    Write-Host "  python -m facekey service" -ForegroundColor White
    Write-Host ""
    Write-Host "To unregister:" -ForegroundColor Yellow
    Write-Host "  .\register.ps1 -Unregister" -ForegroundColor White
}
