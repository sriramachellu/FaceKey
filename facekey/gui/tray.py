"""System tray app — background face authentication with taskbar icon."""

import ctypes
import threading
import time
from enum import Enum

import pystray
from PIL import Image, ImageDraw, ImageFont

from facekey.auth.fast_pipeline import FastPipeline
from facekey.auth.pipeline import AuthStatus
from facekey.config import DEFAULT_CAMERA_INDEX
from facekey.storage import EmbeddingVault


class TrayState(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"
    NO_PROFILES = "no_profiles"
    ERROR = "error"


ICON_COLORS = {
    TrayState.IDLE: ("#0078D4", "#FFFFFF"),
    TrayState.SCANNING: ("#0078D4", "#FFFFFF"),
    TrayState.AUTHENTICATED: ("#0F7B0F", "#FFFFFF"),
    TrayState.FAILED: ("#C42B1C", "#FFFFFF"),
    TrayState.NO_PROFILES: ("#808080", "#FFFFFF"),
    TrayState.ERROR: ("#C42B1C", "#FFFFFF"),
}


class FaceKeyTray:
    """System tray application for FaceKey."""

    def __init__(self, force_cpu: bool = False, camera_index: int = DEFAULT_CAMERA_INDEX):
        self._force_cpu = force_cpu
        self._camera_index = camera_index
        self._state = TrayState.IDLE
        self._pipeline: FastPipeline | None = None
        self._scan_thread: threading.Thread | None = None
        self._scanning = False
        self._icon: pystray.Icon | None = None
        self._last_result_text = ""

    def run(self):
        vault = EmbeddingVault()
        profiles = vault.list_profiles()
        if not profiles:
            self._state = TrayState.NO_PROFILES
            self._last_result_text = "No enrolled profiles"
        else:
            self._last_result_text = f"Profiles: {', '.join(profiles)}"

        self._icon = pystray.Icon(
            "FaceKey",
            icon=self._create_icon(),
            title="FaceKey",
            menu=self._build_menu(),
        )
        self._icon.run()

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(
                lambda _: self._last_result_text,
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Scanning", self._on_start_scan,
                             visible=lambda _: not self._scanning),
            pystray.MenuItem("Stop Scanning", self._on_stop_scan,
                             visible=lambda _: self._scanning),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Enroll Face...", self._on_enroll),
            pystray.MenuItem("Verify Window...", self._on_verify),
            pystray.MenuItem("Profiles...", self._on_profiles),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )

    def _create_icon(self) -> Image.Image:
        bg, fg = ICON_COLORS.get(self._state, ICON_COLORS[TrayState.IDLE])
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Rounded square background
        draw.rounded_rectangle(
            (2, 2, size - 2, size - 2),
            radius=14,
            fill=bg,
        )

        # Simplified face icon
        cx, cy = size // 2, size // 2

        if self._state == TrayState.AUTHENTICATED:
            # Checkmark
            draw.line(
                [(cx - 12, cy), (cx - 3, cy + 10), (cx + 14, cy - 12)],
                fill=fg, width=4,
            )
        elif self._state == TrayState.FAILED:
            # X mark
            draw.line([(cx - 10, cy - 10), (cx + 10, cy + 10)], fill=fg, width=4)
            draw.line([(cx + 10, cy - 10), (cx - 10, cy + 10)], fill=fg, width=4)
        else:
            # Face outline
            draw.ellipse(
                (cx - 12, cy - 16, cx + 12, cy + 8),
                outline=fg, width=2,
            )
            # Eyes
            draw.ellipse((cx - 7, cy - 8, cx - 3, cy - 4), fill=fg)
            draw.ellipse((cx + 3, cy - 8, cx + 7, cy - 4), fill=fg)
            # Mouth
            if self._state == TrayState.SCANNING:
                draw.arc((cx - 6, cy - 2, cx + 6, cy + 6), 0, 180, fill=fg, width=2)

        return img

    def _update_icon(self):
        if self._icon:
            self._icon.icon = self._create_icon()
            self._icon.update_menu()

    def _on_start_scan(self, icon=None, item=None):
        if self._scanning:
            return

        vault = EmbeddingVault()
        if not vault.list_profiles():
            self._state = TrayState.NO_PROFILES
            self._last_result_text = "No enrolled profiles — enroll first"
            self._update_icon()
            return

        self._scanning = True
        self._state = TrayState.SCANNING
        self._last_result_text = "Scanning..."
        self._update_icon()

        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._scan_thread.start()

    def _on_stop_scan(self, icon=None, item=None):
        self._scanning = False
        if self._pipeline:
            self._pipeline.shutdown()
            self._pipeline = None
        self._state = TrayState.IDLE
        self._last_result_text = "Stopped"
        self._update_icon()

    def _scan_loop(self):
        try:
            self._pipeline = FastPipeline(
                force_cpu=self._force_cpu,
                camera_index=self._camera_index,
                process_interval=3,
                cache_frames=30,
            )
            self._pipeline.initialize()

            while self._scanning:
                frame, result = self._pipeline.process_frame()

                if result is None:
                    time.sleep(0.016)
                    continue

                if result.status == AuthStatus.SUCCESS:
                    self._state = TrayState.AUTHENTICATED
                    sim_text = f"{result.similarity:.2f}"
                    self._last_result_text = (
                        f"Authenticated: {result.profile_name} "
                        f"(sim={sim_text}, {result.elapsed_ms:.0f}ms)"
                    )
                elif result.status == AuthStatus.NO_FACE:
                    self._state = TrayState.SCANNING
                    self._last_result_text = "Scanning... no face"
                elif result.status == AuthStatus.NO_MATCH:
                    self._state = TrayState.FAILED
                    self._last_result_text = f"No match (sim={result.similarity:.2f})"
                elif result.status == AuthStatus.LOCKED_OUT:
                    self._state = TrayState.FAILED
                    self._last_result_text = "Locked out — too many failures"

                self._update_icon()
                time.sleep(0.033)

        except Exception as e:
            self._state = TrayState.ERROR
            self._last_result_text = f"Error: {e}"
            self._update_icon()
        finally:
            if self._pipeline:
                self._pipeline.shutdown()
                self._pipeline = None
            self._scanning = False

    def _on_enroll(self, icon=None, item=None):
        threading.Thread(target=self._launch_enroll, daemon=True).start()

    def _launch_enroll(self):
        from facekey.gui.enrollment import run_enrollment
        # Stop scanning while enrolling
        was_scanning = self._scanning
        if was_scanning:
            self._on_stop_scan()
            time.sleep(0.5)

        run_enrollment(force_cpu=self._force_cpu, camera_index=self._camera_index)

        vault = EmbeddingVault()
        profiles = vault.list_profiles()
        self._last_result_text = f"Profiles: {', '.join(profiles)}" if profiles else "No enrolled profiles"
        self._state = TrayState.IDLE
        self._update_icon()

    def _on_verify(self, icon=None, item=None):
        threading.Thread(target=self._launch_verify, daemon=True).start()

    def _launch_verify(self):
        was_scanning = self._scanning
        if was_scanning:
            self._on_stop_scan()
            time.sleep(0.5)

        from facekey.gui.verify import run_verify
        run_verify(force_cpu=self._force_cpu, camera_index=self._camera_index)

        self._state = TrayState.IDLE
        self._update_icon()

    def _on_profiles(self, icon=None, item=None):
        vault = EmbeddingVault()
        profiles = vault.list_profiles()
        if profiles:
            self._last_result_text = f"Profiles: {', '.join(profiles)}"
        else:
            self._last_result_text = "No enrolled profiles"
        self._update_icon()

    def _on_quit(self, icon=None, item=None):
        self._scanning = False
        if self._pipeline:
            self._pipeline.shutdown()
        if self._icon:
            self._icon.stop()


def run_tray(force_cpu: bool = False, camera_index: int = DEFAULT_CAMERA_INDEX):
    """Launch the system tray app."""
    tray = FaceKeyTray(force_cpu=force_cpu, camera_index=camera_index)
    tray.run()
