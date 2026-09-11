"""Verification window — real-time face matching with Glance-style UI."""

import threading
import time

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageTk

from facekey.auth import AuthPipeline
from facekey.auth.pipeline import AuthStatus
from facekey.camera import Camera
from facekey.config import DEFAULT_CAMERA_INDEX
from facekey.storage import EmbeddingVault
from facekey.gui.theme import (
    ACCENT, SUCCESS, ERROR, WARNING,
    WINDOW_WIDTH, WINDOW_HEIGHT, CORNER_RADIUS, PREVIEW_SIZE,
    TEXT_SECONDARY_LIGHT, TEXT_SECONDARY_DARK,
)

STATUS_CONFIG = {
    AuthStatus.SUCCESS: (SUCCESS, "Access Granted"),
    AuthStatus.NO_FACE: ("#808080", "No Face Detected"),
    AuthStatus.NO_MATCH: (ERROR, "No Match"),
    AuthStatus.SPOOF_DETECTED: (ERROR, "Spoof Detected"),
    AuthStatus.LOCKED_OUT: (ERROR, "Locked Out"),
    AuthStatus.LIVENESS_FAILED: (WARNING, "Liveness Failed"),
}


class VerifyWindow(ctk.CTkToplevel):
    """Real-time face verification window."""

    def __init__(self, master=None, force_cpu: bool = False,
                 camera_index: int = DEFAULT_CAMERA_INDEX,
                 on_close=None):
        super().__init__(master)

        self.title("FaceKey — Verify")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._force_cpu = force_cpu
        self._camera_index = camera_index
        self._on_close_cb = on_close
        self._camera: Camera | None = None
        self._pipeline: AuthPipeline | None = None
        self._running = False

        self._build_ui()
        self._start()

    def _build_ui(self):
        self.configure(fg_color=("gray95", "#1A1A1A"))

        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(pady=(24, 0), padx=32, fill="x")

        ctk.CTkLabel(
            header, text="FaceKey",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            header, text="Looking for you...",
            font=ctk.CTkFont(size=14),
            text_color=(TEXT_SECONDARY_LIGHT, TEXT_SECONDARY_DARK),
        ).pack(anchor="w", pady=(2, 0))

        # --- Circular preview ---
        preview_frame = ctk.CTkFrame(self, fg_color="transparent")
        preview_frame.pack(pady=(20, 0))

        self._canvas = ctk.CTkCanvas(
            preview_frame,
            width=PREVIEW_SIZE + 16,
            height=PREVIEW_SIZE + 16,
            highlightthickness=0,
            bg=self._apply_color(("gray95", "#1A1A1A")),
        )
        self._canvas.pack()

        # --- Status ---
        self._match_label = ctk.CTkLabel(
            self, text="Initializing...",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self._match_label.pack(pady=(20, 0))

        self._detail_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=13),
            text_color=(TEXT_SECONDARY_LIGHT, TEXT_SECONDARY_DARK),
        )
        self._detail_label.pack(pady=(4, 0))

        # --- Stats row ---
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(pady=(20, 0), padx=48, fill="x")

        self._sim_card = self._make_stat_card(stats_frame, "Similarity", "—")
        self._sim_card.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self._spoof_card = self._make_stat_card(stats_frame, "Real Score", "—")
        self._spoof_card.pack(side="left", expand=True, fill="x", padx=(4, 4))

        self._latency_card = self._make_stat_card(stats_frame, "Latency", "—")
        self._latency_card.pack(side="left", expand=True, fill="x", padx=(4, 0))

        # --- Close button ---
        ctk.CTkButton(
            self,
            text="Close",
            height=46,
            corner_radius=CORNER_RADIUS,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ACCENT,
            command=self._on_close,
        ).pack(pady=(24, 24), padx=48, fill="x")

    def _make_stat_card(self, parent, label, value):
        card = ctk.CTkFrame(
            parent, corner_radius=10,
            fg_color=("white", "#2D2D2D"),
        )
        ctk.CTkLabel(
            card, text=label,
            font=ctk.CTkFont(size=11),
            text_color=(TEXT_SECONDARY_LIGHT, TEXT_SECONDARY_DARK),
        ).pack(pady=(10, 0))
        val_label = ctk.CTkLabel(
            card, text=value,
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        val_label.pack(pady=(2, 10))
        card._val_label = val_label
        return card

    def _apply_color(self, color_pair):
        mode = ctk.get_appearance_mode()
        if isinstance(color_pair, tuple):
            return color_pair[1] if mode == "Dark" else color_pair[0]
        return color_pair

    def _start(self):
        self._running = True
        threading.Thread(target=self._init_pipeline, daemon=True).start()

    def _init_pipeline(self):
        vault = EmbeddingVault()
        if not vault.list_profiles():
            self.after(0, lambda: self._match_label.configure(text="No enrolled profiles"))
            return

        self._pipeline = AuthPipeline(vault=vault, force_cpu=self._force_cpu)
        self._camera = Camera(index=self._camera_index)
        self._camera.open()

        time.sleep(1.5)
        for _ in range(10):
            self._camera.read()

        self.after(0, self._update_frame)

    def _update_frame(self):
        if not self._running or self._camera is None or self._pipeline is None:
            return

        try:
            frame = self._camera.read()
        except Exception:
            self.after(33, self._update_frame)
            return

        result = self._pipeline.authenticate_frame(frame)
        display = cv2.flip(frame, 1)

        # Ring color based on status
        color, label = STATUS_CONFIG.get(
            result.status, (ACCENT, str(result.status.value))
        )

        if result.profile_name:
            label = f"{result.profile_name}"

        self._match_label.configure(text=label, text_color=color)

        # Detail line
        detail_parts = []
        if result.status == AuthStatus.SUCCESS:
            detail_parts.append("Access Granted")
            if result.liveness_passed:
                detail_parts.append("Liveness: PASS")
            else:
                detail_parts.append("Liveness: pending...")
        self._detail_label.configure(text=" · ".join(detail_parts))

        # Stats
        if result.similarity > 0:
            self._sim_card._val_label.configure(text=f"{result.similarity:.2f}")
        if result.spoof_score > 0:
            self._spoof_card._val_label.configure(text=f"{result.spoof_score:.2f}")
        self._latency_card._val_label.configure(text=f"{result.elapsed_ms:.0f}ms")

        # Render preview
        self._render_preview(display, color)

        self.after(33, self._update_frame)

    def _render_preview(self, display, ring_color):
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        w, h = pil_img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        pil_img = pil_img.crop((left, top, left + side, top + side))
        pil_img = pil_img.resize((PREVIEW_SIZE, PREVIEW_SIZE), Image.LANCZOS)

        mask = Image.new("L", (PREVIEW_SIZE, PREVIEW_SIZE), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, PREVIEW_SIZE, PREVIEW_SIZE), fill=255)
        pil_img.putalpha(mask)

        canvas_size = PREVIEW_SIZE + 16
        bg_color = self._apply_color(("#F2F2F2", "#1A1A1A"))
        result = Image.new("RGBA", (canvas_size, canvas_size),
                           bg_color + "FF" if len(bg_color) == 7 else bg_color)

        ring_img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(ring_img)

        r_hex = ring_color.lstrip("#")
        r_rgb = tuple(int(r_hex[i:i+2], 16) for i in (0, 2, 4))
        ring_draw.ellipse((0, 0, canvas_size - 1, canvas_size - 1), fill=(*r_rgb, 255))
        inner_offset = 4
        ring_draw.ellipse(
            (inner_offset, inner_offset, canvas_size - 1 - inner_offset, canvas_size - 1 - inner_offset),
            fill=(0, 0, 0, 0),
        )

        result.paste(ring_img, (0, 0), ring_img)
        offset = (canvas_size - PREVIEW_SIZE) // 2
        result.paste(pil_img, (offset, offset), pil_img)

        self._photo = ImageTk.PhotoImage(result)
        self._canvas.delete("all")
        self._canvas.create_image(canvas_size // 2, canvas_size // 2, image=self._photo)

    def _on_close(self):
        self._running = False
        if self._camera:
            try:
                self._camera.close()
            except Exception:
                pass
            self._camera = None
        if self._on_close_cb:
            self._on_close_cb()
        self.destroy()


def run_verify(force_cpu: bool = False, camera_index: int = DEFAULT_CAMERA_INDEX):
    """Standalone verification launcher."""
    from facekey.gui.theme import apply_theme

    apply_theme()
    root = ctk.CTk()
    root.withdraw()

    window = VerifyWindow(
        root, force_cpu=force_cpu, camera_index=camera_index,
        on_close=root.quit,
    )
    window.protocol("WM_DELETE_WINDOW", lambda: (window._on_close(), root.quit()))

    root.mainloop()
    root.destroy()
