"""Quick auth window — opens camera, authenticates, auto-closes on success.

Used by the named pipe service and credential provider. Shows a small
Glance-style face circle while scanning, then flashes green on success.
"""

import json
import threading
import time

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageTk

from facekey.camera import Camera
from facekey.config import DEFAULT_CAMERA_INDEX, SIMILARITY_THRESHOLD
from facekey.detection import FaceDetector
from facekey.gui.theme import ACCENT, SUCCESS
from facekey.recognition import FaceEmbedder
from facekey.antispoof import AntiSpoof
from facekey.storage import EmbeddingVault


class AuthWindow(ctk.CTkToplevel):
    """Compact auth window for lock-screen style face unlock."""

    WINDOW_SIZE = 340

    def __init__(self, master, force_cpu=False, camera_index=DEFAULT_CAMERA_INDEX,
                 timeout=15, on_result=None):
        super().__init__(master)

        self.title("FaceKey")
        self.geometry(f"{self.WINDOW_SIZE}x{self.WINDOW_SIZE + 80}")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._force_cpu = force_cpu
        self._camera_index = camera_index
        self._timeout = timeout
        self._on_result = on_result
        self._running = False
        self._result = None

        self._camera = None
        self._detector = None
        self._embedder = None
        self._antispoof = None
        self._vault = None
        self._deadline = None
        self._warmup_done = False

        preview_size = 220
        self._preview_size = preview_size
        self._circle_mask = Image.new("L", (preview_size, preview_size), 0)
        ImageDraw.Draw(self._circle_mask).ellipse(
            (0, 0, preview_size, preview_size), fill=255,
        )
        self._ring_cache = {}

        self._build_ui()
        self._start()

    def _build_ui(self):
        self.configure(fg_color=("gray95", "#1A1A1A"))

        ctk.CTkLabel(
            self, text="FaceKey",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(16, 0))

        self._status = ctk.CTkLabel(
            self, text="Starting camera...",
            font=ctk.CTkFont(size=13),
            text_color=("#6B6B6B", "#9A9A9A"),
        )
        self._status.pack(pady=(4, 8))

        canvas_size = self._preview_size + 12
        self._canvas = ctk.CTkCanvas(
            self, width=canvas_size, height=canvas_size,
            highlightthickness=0,
            bg=self._color(("gray95", "#1A1A1A")),
        )
        self._canvas.pack()

        self._sim_label = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=12),
            text_color=("#6B6B6B", "#9A9A9A"),
        )
        self._sim_label.pack(pady=(8, 0))

    def _color(self, pair):
        return pair[1] if ctk.get_appearance_mode() == "Dark" else pair[0]

    def _start(self):
        self._running = True
        threading.Thread(target=self._init_pipeline, daemon=True).start()

    def _init_pipeline(self):
        """Background thread: open camera + load models, then hand off to main thread."""
        try:
            self._camera = Camera(index=self._camera_index)
            self._camera.open()

            self.after(0, lambda: self._status.configure(text="Loading models..."))

            self._detector = FaceDetector()
            self._embedder = FaceEmbedder(force_cpu=self._force_cpu)
            self._antispoof = AntiSpoof(force_cpu=self._force_cpu)
            self._vault = EmbeddingVault()

            self._deadline = time.time() + self._timeout
            self._warmup_done = True

            self.after(0, self._update_preview)

        except Exception as e:
            self._result = {"status": "error", "reason": str(e)}
            self.after(0, self._finish)

    def _update_preview(self):
        """Main-thread loop: read camera, detect, verify, render."""
        if not self._running or self._camera is None:
            return

        if time.time() > self._deadline:
            self._camera.close()
            self._result = {"status": "failure", "reason": "timeout"}
            self._status.configure(text="Timed out", text_color="#C42B1C")
            self.after(1000, self._finish)
            return

        try:
            frame = self._camera.read()
        except Exception:
            self.after(33, self._update_preview)
            return

        display = cv2.flip(frame, 1)
        face = self._detector.detect_largest(frame)

        if face is None:
            self._render(display, "#808080")
            self._status.configure(text="Looking for you...")
            self.after(33, self._update_preview)
            return

        self._render(display, ACCENT)
        self._status.configure(text="Verifying...")

        is_real, spoof_score = self._antispoof.predict(frame, face["bbox"])

        aligned = self._detector.align_face(frame, face["landmarks"])
        embedding = self._embedder.get_embedding(aligned)

        all_profiles = self._vault.get_all_embeddings()
        best_name, best_sim = None, -1.0
        for name, embeddings in all_profiles.items():
            for stored in embeddings:
                sim = float(np.dot(embedding, stored))
                if sim > best_sim:
                    best_sim = sim
                    best_name = name

        if best_sim >= SIMILARITY_THRESHOLD and best_name is not None:
            self._result = {
                "status": "success",
                "user": best_name,
                "similarity": round(best_sim, 3),
                "spoof_score": round(spoof_score, 3),
            }
            self._show_success(self._result, display)
            self._camera.close()
            self.after(1500, self._finish)
            return

        if best_sim > 0:
            self._sim_label.configure(text=f"sim={best_sim:.2f}")

        self.after(33, self._update_preview)

    def _show_success(self, result, display):
        self._render(display, SUCCESS)
        self._status.configure(text=f"Welcome, {result['user']}!", text_color=SUCCESS)
        self._sim_label.configure(text=f"Similarity: {result['similarity']:.2f}")

    def _get_ring(self, color):
        if color in self._ring_cache:
            return self._ring_cache[color]
        cs = self._preview_size + 12
        ring = Image.new("RGBA", (cs, cs), (0, 0, 0, 0))
        draw = ImageDraw.Draw(ring)
        r = tuple(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        draw.ellipse((0, 0, cs - 1, cs - 1), fill=(*r, 255))
        draw.ellipse((3, 3, cs - 4, cs - 4), fill=(0, 0, 0, 0))
        self._ring_cache[color] = ring
        return ring

    def _render(self, display, ring_color):
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w-side)//2, (h-side)//2, (w+side)//2, (h+side)//2))
        img = img.resize((self._preview_size, self._preview_size), Image.BILINEAR)
        img.putalpha(self._circle_mask)

        cs = self._preview_size + 12
        bg = self._color(("#F2F2F2", "#1A1A1A"))
        result = Image.new("RGBA", (cs, cs), bg + "FF" if len(bg) == 7 else bg)
        result.paste(self._get_ring(ring_color), (0, 0), self._get_ring(ring_color))
        off = (cs - self._preview_size) // 2
        result.paste(img, (off, off), img)

        self._photo = ImageTk.PhotoImage(result)
        self._canvas.delete("all")
        self._canvas.create_image(cs // 2, cs // 2, image=self._photo)

    def _finish(self):
        if self._on_result and self._result:
            self._on_result(self._result)
        self.destroy()

    def _cancel(self):
        self._running = False
        if self._camera:
            self._camera.close()
        self._result = {"status": "failure", "reason": "cancelled"}
        self._finish()


def run_auth(force_cpu=False, camera_index=DEFAULT_CAMERA_INDEX,
             timeout=15, pipe_output=False):
    """Launch auth window. If pipe_output=True, prints JSON result to stdout."""
    from facekey.gui.theme import apply_theme
    apply_theme()

    root = ctk.CTk()
    root.withdraw()

    result_holder = [None]

    def on_result(result):
        result_holder[0] = result
        root.quit()

    window = AuthWindow(
        root, force_cpu=force_cpu, camera_index=camera_index,
        timeout=timeout, on_result=on_result,
    )
    window.protocol("WM_DELETE_WINDOW", lambda: (window._cancel(), root.quit()))

    root.mainloop()
    root.destroy()

    result = result_holder[0] or {"status": "error", "reason": "no_result"}

    if pipe_output:
        print(json.dumps(result))
    else:
        if result["status"] == "success":
            print(f"Authenticated: {result['user']} (sim={result['similarity']})")
        else:
            print(f"Auth failed: {result.get('reason', 'unknown')}")

    return result
