"""Compatibility entry point for the ServoLab desktop application."""

from .ui.application import run
from .ui.main_window import ServoLabWindow

__all__ = ["ServoLabWindow", "run"]
