"""Enrollment window — capture face samples with a Glance-style circular preview."""

import threading
import time

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageTk

from facekey.camera import Camera
from facekey.config import DEFAULT_CAMERA_INDEX
from facekey.detection import FaceDetector
from facekey.recognition import FaceEmbedder
from facekey.storage import EmbeddingVault
from facekey.gui.theme import (
    ACCENT, ACCENT_HOVER, SUCCESS, ERROR, WARNING,
    WINDOW_WIDTH, WINDOW_HEIGHT, CORNER_RADIUS, PREVIEW_SIZE,
    TEXT_SECONDARY_LIGHT, TEXT_SECONDARY_DARK,
)

DIRECTIONS = [
    ("Look straight at the camera", "center"),
    ("Slowly turn left", "left"),
    ("Slowly turn right", "right"),
    ("Tilt your head up slightly", "up"),
    ("Tilt your head down slightly", "down"),
]
NUM_CAPTURES = 5


class EnrollmentWindow(ctk.CTkToplevel):
    """Face enrollment window with circular camera preview."""

    def __init__(self, master=None, force_cpu: bool = False,
                 camera_index: int = DEFAULT_CAMERA_INDEX,
                 on_complete=None):
        super().__init__(master)

        self.title("FaceKey — Enroll")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._force_cpu = force_cpu
        self._camera_index = camera_index
        self._on_complete = on_complete

        self._camera: Camera | None = None
        self._detector: FaceDetector | None = None
        self._embedder: FaceEmbedder | None = None
        self._vault = EmbeddingVault()

        self._embeddings: list[np.ndarray] = []
        self._capture_index = 0
        self._running = False
        self._face_detected = False
        self._countdown_active = False

        self._build_ui()

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
            header, text="Enroll your face for quick unlock",
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

        # --- Direction instruction ---
        self._direction_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._direction_label.pack(pady=(16, 0))

        self._status_label = ctk.CTkLabel(
            self, text="Enter a profile name to begin",
            font=ctk.CTkFont(size=13),
            text_color=(TEXT_SECONDARY_LIGHT, TEXT_SECONDARY_DARK),
        )
        self._status_label.pack(pady=(4, 0))

        # --- Progress dots ---
        dots_frame = ctk.CTkFrame(self, fg_color="transparent")
        dots_frame.pack(pady=(16, 0))

        self._dots = []
        for i in range(NUM_CAPTURES):
            dot = ctk.CTkFrame(
                dots_frame,
                width=12, height=12,
                corner_radius=6,
                fg_color=("gray75", "gray40"),
            )
            dot.pack(side="left", padx=4)
            self._dots.append(dot)

        # --- Profile name input ---
        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.pack(pady=(20, 0), padx=48, fill="x")

        self._name_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Profile name (e.g. default)",
            height=42,
            corner_radius=CORNER_RADIUS,
            font=ctk.CTkFont(size=14),
        )
        self._name_entry.pack(fill="x")
        self._name_entry.insert(0, "default")

        # --- Action button ---
        self._action_btn = ctk.CTkButton(
            self,
            text="Start Enrollment",
            height=46,
            corner_radius=CORNER_RADIUS,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._on_action,
        )
        self._action_btn.pack(pady=(20, 0), padx=48, fill="x")

        # --- Cancel link ---
        self._cancel_btn = ctk.CTkButton(
            self,
            text="Cancel",
            height=36,
            corner_radius=CORNER_RADIUS,
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            hover_color=("gray85", "gray25"),
            text_color=(TEXT_SECONDARY_LIGHT, TEXT_SECONDARY_DARK),
            command=self._on_close,
        )
        self._cancel_btn.pack(pady=(8, 24), padx=48, fill="x")

        self._draw_empty_preview()

    def _apply_color(self, color_pair):
        mode = ctk.get_appearance_mode()
        if isinstance(color_pair, tuple):
            return color_pair[1] if mode == "Dark" else color_pair[0]
        return color_pair

    def _draw_empty_preview(self):
        size = PREVIEW_SIZE + 16
        bg = self._apply_color(("gray95", "#1A1A1A"))
        self._canvas.configure(bg=bg)
        self._canvas.delete("all")

        cx, cy = size // 2, size // 2
        r = PREVIEW_SIZE // 2

        self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=self._apply_color(("#E5E5E5", "#2D2D2D")),
            outline=self._apply_color(("#D0D0D0", "#404040")),
            width=2,
        )

        # Face placeholder icon
        self._canvas.create_oval(
            cx - 30, cy - 45, cx + 30, cy + 15,
            fill=self._apply_color(("#C0C0C0", "#505050")),
            outline="",
        )
        self._canvas.create_oval(
            cx - 50, cy + 10, cx + 50, cy + 65,
            fill=self._apply_color(("#C0C0C0", "#505050")),
            outline="",
        )

    def _on_action(self):
        if not self._running:
            self._start_enrollment()
        elif self._face_detected and not self._countdown_active:
            self._capture_sample()

    def _start_enrollment(self):
        name = self._name_entry.get().strip() or "default"

        if self._vault.profile_exists(name):
            self._vault.delete_profile(name)

        self._name_entry.configure(state="disabled")
        self._action_btn.configure(text="Initializing...", state="disabled")
        self._status_label.configure(text="Starting camera...")

        self._running = True
        threading.Thread(target=self._init_pipeline, args=(name,), daemon=True).start()

    def _init_pipeline(self, profile_name: str):
        self._profile_name = profile_name
        self._detector = FaceDetector()
        self._embedder = FaceEmbedder(force_cpu=self._force_cpu)
        self._camera = Camera(index=self._camera_index)
        self._camera.open()

        # Camera warmup
        time.sleep(1.5)
        for _ in range(10):
            self._camera.read()

        self.after(0, self._begin_captures)

    def _begin_captures(self):
        self._capture_index = 0
        self._update_direction()
        self._action_btn.configure(text="Capture", state="normal")
        self._update_preview()

    def _update_direction(self):
        if self._capture_index < NUM_CAPTURES:
            text, _ = DIRECTIONS[self._capture_index]
            self._direction_label.configure(text=text)
            self._status_label.configure(
                text=f"Sample {self._capture_index + 1} of {NUM_CAPTURES} — hold still"
            )

    def _update_preview(self):
        if not self._running or self._camera is None:
            return

        try:
            frame = self._camera.read()
        except Exception:
            self.after(33, self._update_preview)
            return

        display = cv2.flip(frame, 1)
        self._current_frame = frame

        face = self._detector.detect_largest(frame)
        self._face_detected = face is not None
        self._current_face = face

        ring_color = ACCENT
        if face is not None:
            ring_color = SUCCESS
            self._action_btn.configure(state="normal")
        else:
            ring_color = ERROR
            if not self._countdown_active:
                self._action_btn.configure(state="disabled")

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        # Crop to square center
        w, h = pil_img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        pil_img = pil_img.crop((left, top, left + side, top + side))
        pil_img = pil_img.resize((PREVIEW_SIZE, PREVIEW_SIZE), Image.LANCZOS)

        # Create circular mask
        mask = Image.new("L", (PREVIEW_SIZE, PREVIEW_SIZE), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, PREVIEW_SIZE, PREVIEW_SIZE), fill=255)
        pil_img.putalpha(mask)

        # Draw onto canvas-sized image with ring
        canvas_size = PREVIEW_SIZE + 16
        bg_color = self._apply_color(("#F2F2F2", "#1A1A1A"))
        result = Image.new("RGBA", (canvas_size, canvas_size), bg_color + "FF" if len(bg_color) == 7 else bg_color)

        ring_img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(ring_img)

        # Ring
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

        self.after(33, self._update_preview)

    def _capture_sample(self):
        if self._current_face is None or self._countdown_active:
            return

        self._countdown_active = True
        self._action_btn.configure(state="disabled")
        self._status_label.configure(text="Capturing...")

        frame = self._current_frame
        face = self._current_face

        aligned = self._detector.align_face(frame, face["landmarks"])
        embedding = self._embedder.get_embedding(aligned)
        self._embeddings.append(embedding)

        # Update dot
        self._dots[self._capture_index].configure(fg_color=SUCCESS)
        self._capture_index += 1

        self._countdown_active = False

        if self._capture_index >= NUM_CAPTURES:
            self._finish_enrollment()
        else:
            self._update_direction()
            self._action_btn.configure(text="Capture", state="normal")

    def _finish_enrollment(self):
        self._vault.save_profile(self._profile_name, self._embeddings)

        self._direction_label.configure(text="Enrollment Complete!")
        self._status_label.configure(
            text=f"Profile '{self._profile_name}' saved with {len(self._embeddings)} samples"
        )
        self._action_btn.configure(
            text="Done",
            fg_color=SUCCESS,
            hover_color="#0A5F0A",
            command=self._on_done,
            state="normal",
        )
        self._cancel_btn.pack_forget()

    def _on_done(self):
        self._stop_camera()
        if self._on_complete:
            self._on_complete(self._profile_name, len(self._embeddings))
        self.destroy()

    def _on_close(self):
        self._running = False
        self._stop_camera()
        self.destroy()

    def _stop_camera(self):
        self._running = False
        if self._camera is not None:
            try:
                self._camera.close()
            except Exception:
                pass
            self._camera = None


def run_enrollment(force_cpu: bool = False, camera_index: int = DEFAULT_CAMERA_INDEX):
    """Standalone enrollment launcher."""
    from facekey.gui.theme import apply_theme

    apply_theme()
    root = ctk.CTk()
    root.withdraw()

    def on_complete(name, count):
        print(f"Enrolled '{name}' with {count} samples.")
        root.quit()

    window = EnrollmentWindow(
        root, force_cpu=force_cpu, camera_index=camera_index,
        on_complete=on_complete,
    )
    window.protocol("WM_DELETE_WINDOW", lambda: (window._on_close(), root.quit()))

    root.mainloop()
    root.destroy()
