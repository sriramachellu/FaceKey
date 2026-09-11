# Building the FaceKey Credential Provider

## Prerequisites

1. **Visual Studio Build Tools 2022** (or full Visual Studio 2022)
   - Download: https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022
   - Select "Desktop development with C++" workload
   - Required components: MSVC v143, Windows 11 SDK

2. **CMake 3.20+**
   - Included with VS Build Tools, or install from https://cmake.org

## Build

Open "Developer Command Prompt for VS 2022" (or "x64 Native Tools Command Prompt"):

```cmd
cd credential_provider
cmake -B build -A x64
cmake --build build --config Release
```

The DLL is output to `build/bin/Release/FaceKeyProvider.dll`.

## Install

Run PowerShell as Administrator:

```powershell
cd credential_provider
.\register.ps1
```

This copies the DLL to `C:\Windows\System32` and registers the COM object.

## Uninstall

```powershell
cd credential_provider
.\register.ps1 -Unregister
```

## How it works

1. Windows loads `FaceKeyProvider.dll` at the logon/lock screen
2. The DLL connects to the FaceKey named pipe (`\\.\pipe\FaceKey`)
3. If the service is running and profiles exist, a "FaceKey" tile appears
4. When selected, it sends an auth request through the pipe
5. The FaceKey service launches the auth window (camera + face matching)
6. On success, the credential provider submits Windows credentials
7. On failure, a password field appears as fallback

## Prerequisites for runtime

The FaceKey Python service must be running before locking the screen:

```cmd
python -m facekey service
```

For auto-start, add a scheduled task or startup shortcut.
