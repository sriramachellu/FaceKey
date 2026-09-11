r"""Named pipe server for credential provider communication.

Protocol (JSON over \\.\pipe\FaceKey):
  Request:  {"command": "authenticate", "timeout": 10}
  Response: {"status": "success", "user": "name", "similarity": 0.87}
         or {"status": "failure", "reason": "no_match"}
         or {"status": "error", "reason": "..."}

  Request:  {"command": "status"}
  Response: {"status": "ready", "profiles": ["name1"], "gpu": true}

  Request:  {"command": "shutdown"}
  Response: {"status": "ok"}
"""

import json
import logging
import time

import win32file
import win32pipe
import win32security
import pywintypes

from facekey.config import DEFAULT_CAMERA_INDEX
from facekey.storage import EmbeddingVault

logger = logging.getLogger("facekey.service")

PIPE_NAME = r"\\.\pipe\FaceKey"
PIPE_BUFFER_SIZE = 4096
AUTH_TIMEOUT_DEFAULT = 10


class AuthService:
    """Named pipe server that handles auth requests from the credential provider."""

    def __init__(self, force_cpu: bool = False, camera_index: int = DEFAULT_CAMERA_INDEX):
        self._force_cpu = force_cpu
        self._camera_index = camera_index
        self._running = False

    def start(self):
        """Start the auth service (blocking)."""
        logger.info("FaceKey Auth Service starting...")
        self._running = True

        while self._running:
            pipe_handle = None
            try:
                # Create security attributes allowing access from SYSTEM and interactive users
                sa = _create_pipe_security()

                pipe_handle = win32pipe.CreateNamedPipe(
                    PIPE_NAME,
                    win32pipe.PIPE_ACCESS_DUPLEX,
                    (win32pipe.PIPE_TYPE_MESSAGE
                     | win32pipe.PIPE_READMODE_MESSAGE
                     | win32pipe.PIPE_WAIT),
                    win32pipe.PIPE_UNLIMITED_INSTANCES,
                    PIPE_BUFFER_SIZE,
                    PIPE_BUFFER_SIZE,
                    0,
                    sa,
                )

                logger.info("Waiting for client connection...")
                win32pipe.ConnectNamedPipe(pipe_handle, None)
                logger.info("Client connected")

                self._handle_client(pipe_handle)

            except pywintypes.error as e:
                if not self._running:
                    break
                logger.error(f"Pipe error: {e}")
                time.sleep(1)
            finally:
                if pipe_handle is not None:
                    try:
                        win32pipe.DisconnectNamedPipe(pipe_handle)
                        win32file.CloseHandle(pipe_handle)
                    except Exception:
                        pass

        logger.info("Auth service stopped")

    def stop(self):
        """Signal the service to stop."""
        self._running = False
        # Connect to the pipe to unblock ConnectNamedPipe
        try:
            handle = win32file.CreateFile(
                PIPE_NAME,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None,
                win32file.OPEN_EXISTING, 0, None,
            )
            win32file.CloseHandle(handle)
        except Exception:
            pass

    def _handle_client(self, pipe_handle):
        """Read requests from the pipe and send responses."""
        try:
            while self._running:
                try:
                    _, data = win32file.ReadFile(pipe_handle, PIPE_BUFFER_SIZE)
                    request = json.loads(data.decode("utf-8"))
                except pywintypes.error:
                    break
                except json.JSONDecodeError:
                    self._send(pipe_handle, {"status": "error", "reason": "invalid_json"})
                    continue

                command = request.get("command", "")
                logger.info(f"Received command: {command}")

                if command == "authenticate":
                    timeout = request.get("timeout", AUTH_TIMEOUT_DEFAULT)
                    timeout = max(1, min(int(timeout), 60))
                    response = self._do_authenticate(timeout)
                elif command == "status":
                    response = self._do_status()
                elif command == "shutdown":
                    self._send(pipe_handle, {"status": "ok"})
                    self._running = False
                    break
                else:
                    response = {"status": "error", "reason": f"unknown_command: {command}"}

                self._send(pipe_handle, response)

        except Exception as e:
            logger.error(f"Client handler error: {e}")

    def _send(self, pipe_handle, data: dict):
        try:
            msg = json.dumps(data).encode("utf-8")
            win32file.WriteFile(pipe_handle, msg)
        except Exception as e:
            logger.error(f"Write error: {e}")

    def _do_authenticate(self, timeout: float) -> dict:
        """Launch GUI auth window as subprocess and return its result."""
        import subprocess
        import sys

        try:
            cmd = [
                sys.executable, "-m", "facekey",
                "--camera", str(self._camera_index),
            ]
            if self._force_cpu:
                cmd.append("--cpu")
            cmd += ["auth-window", "--pipe-output", "--timeout", str(int(timeout))]

            logger.info(f"Launching auth window: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 10,
                cwd=None,
            )

            if proc.returncode != 0:
                logger.error(f"Auth window exited {proc.returncode}: {proc.stderr}")
                return {"status": "error", "reason": f"auth_window_exit_{proc.returncode}"}

            stdout = proc.stdout.strip()
            if not stdout:
                return {"status": "error", "reason": "no_output"}

            # Last line is the JSON result
            last_line = stdout.split("\n")[-1].strip()
            result = json.loads(last_line)
            logger.info(f"Auth result: {result.get('status')} user={result.get('user')}")
            return result

        except subprocess.TimeoutExpired:
            logger.warning("Auth window timed out")
            return {"status": "failure", "reason": "timeout"}
        except json.JSONDecodeError as e:
            logger.error(f"Bad JSON from auth window: {e}")
            return {"status": "error", "reason": "invalid_response"}
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return {"status": "error", "reason": str(e)}

    def _do_status(self) -> dict:
        vault = EmbeddingVault()
        profiles = vault.list_profiles()
        from facekey.models import get_device_info
        info = get_device_info()

        return {
            "status": "ready",
            "profiles": profiles,
            "gpu": info.get("has_cuda", False),
            "provider": info.get("active_provider", "unknown"),
        }

def _create_pipe_security():
    """Create security descriptor allowing SYSTEM and authenticated users."""
    sd = win32security.SECURITY_DESCRIPTOR()
    dacl = win32security.ACL()

    # Allow SYSTEM full access
    system_sid = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    dacl.AddAccessAllowedAce(
        win32security.ACL_REVISION,
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        system_sid,
    )

    # Allow authenticated users full access
    auth_sid = win32security.CreateWellKnownSid(win32security.WinAuthenticatedUserSid, None)
    dacl.AddAccessAllowedAce(
        win32security.ACL_REVISION,
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        auth_sid,
    )

    sd.SetSecurityDescriptorDacl(True, dacl, False)

    sa = win32security.SECURITY_ATTRIBUTES()
    sa.SECURITY_DESCRIPTOR = sd
    sa.bInheritHandle = False
    return sa


def run_service(force_cpu: bool = False, camera_index: int = DEFAULT_CAMERA_INDEX):
    """Launch the auth service."""
    import signal

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    service = AuthService(force_cpu=force_cpu, camera_index=camera_index)
    signal.signal(signal.SIGINT, lambda *_: service.stop())
    signal.signal(signal.SIGTERM, lambda *_: service.stop())
    service.start()
