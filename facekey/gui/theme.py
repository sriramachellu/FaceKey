"""FaceKey theme — Windows 11 Fluent-inspired, Glance-style minimalism."""

import customtkinter as ctk

# Windows 11 accent blue
ACCENT = "#0078D4"
ACCENT_HOVER = "#1A86D9"
ACCENT_DARK = "#005A9E"

# Surface colors
SURFACE_LIGHT = "#F3F3F3"
SURFACE_DARK = "#1E1E1E"
CARD_LIGHT = "#FFFFFF"
CARD_DARK = "#2D2D2D"

# Text
TEXT_LIGHT = "#1A1A1A"
TEXT_DARK = "#FFFFFF"
TEXT_SECONDARY_LIGHT = "#6B6B6B"
TEXT_SECONDARY_DARK = "#9A9A9A"

# Status
SUCCESS = "#0F7B0F"
WARNING = "#F7630C"
ERROR = "#C42B1C"

# Sizes
WINDOW_WIDTH = 480
WINDOW_HEIGHT = 680
CORNER_RADIUS = 12
PREVIEW_SIZE = 280


def apply_theme():
    """Configure CustomTkinter for FaceKey."""
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
