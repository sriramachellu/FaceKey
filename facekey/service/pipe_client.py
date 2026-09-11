"""Test client for the named pipe auth service."""

import json
import sys
import time

import win32file
import win32pipe

PIPE_NAME = r"\\.\pipe\FaceKey"


def send_command(command: dict, timeout_ms: int = 30000) -> dict:
    """Connect to the FaceKey pipe and send a command."""
    handle = win32file.CreateFile(
        PIPE_NAME,
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        0, None,
        win32file.OPEN_EXISTING, 0, None,
    )

    win32pipe.SetNamedPipeHandleState(
        handle, win32pipe.PIPE_READMODE_MESSAGE, None, None,
    )

    msg = json.dumps(command).encode("utf-8")
    win32file.WriteFile(handle, msg)

    _, data = win32file.ReadFile(handle, 4096)
    win32file.CloseHandle(handle)

    return json.loads(data.decode("utf-8"))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "auth":
        timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        print(f"Requesting authentication (timeout={timeout}s)...")
        result = send_command({"command": "authenticate", "timeout": timeout})
    elif cmd == "status":
        result = send_command({"command": "status"})
    elif cmd == "shutdown":
        result = send_command({"command": "shutdown"})
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: pipe_client.py [status|auth|shutdown]")
        return

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
