"""Explicit application palettes, independent of the desktop's color scheme."""

from math import cos, pi, sin

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import QApplication


def settings_icon(color: QColor) -> QIcon:
    """A small, palette-aware vector gear with a transparent center."""
    pixmap = QPixmap(36, 36)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    for index in range(32):
        angle = index * 2 * pi / 32
        radius = 8 if index % 4 < 2 else 6.2
        x, y = 9 + radius * cos(angle), 9 + radius * sin(angle)
        if index == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    path.addEllipse(6.2, 6.2, 5.6, 5.6)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillPath(path, color)
    painter.end()
    return QIcon(pixmap)


def apply_theme(theme: str) -> None:
    app = QApplication.instance()
    if app is None:
        return
    app.setStyle("Fusion")
    dark = theme == "dark"
    colors = {
        "Window": "#20242b" if dark else "#f5f6f8",
        "WindowText": "#edf0f5" if dark else "#20242b",
        "Base": "#171b21" if dark else "#ffffff",
        "AlternateBase": "#272d36" if dark else "#edf0f5",
        "Text": "#edf0f5" if dark else "#20242b",
        "Button": "#303743" if dark else "#e9edf3",
        "ButtonText": "#edf0f5" if dark else "#20242b",
        "ToolTipBase": "#303743" if dark else "#ffffff",
        "ToolTipText": "#edf0f5" if dark else "#20242b",
        "Highlight": "#447cba" if dark else "#2463a6",
        "HighlightedText": "#ffffff",
        "Link": "#83b8f4" if dark else "#165eaa",
        "PlaceholderText": "#a0a9b7" if dark else "#657080",
        "Light": "#434c59" if dark else "#ffffff",
        "Midlight": "#363e4a" if dark else "#e9edf3",
        "Mid": "#171b21" if dark else "#bcc4cf",
        "Dark": "#111419" if dark else "#8792a1",
        "Shadow": "#000000" if dark else "#657080",
    }
    palette = QPalette()
    for role, value in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(value))
    for role in ("WindowText", "Text", "ButtonText"):
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            getattr(QPalette.ColorRole, role),
            QColor("#818a98" if dark else "#7b8490"),
        )
    app.setPalette(palette)
