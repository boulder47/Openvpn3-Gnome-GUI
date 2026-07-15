"""A lightweight, dependency-free live bandwidth graph (Cairo on GtkDrawingArea).

Deliberately avoids pulling in a full charting library — this keeps the
Flatpak/Debian/AppImage footprint small and the widget trivially themeable
with the current Libadwaita accent color.
"""

from __future__ import annotations

from collections import deque

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402


class BandwidthGraph(Gtk.DrawingArea):
    """Scrolling line graph of upload/download throughput (bytes/sec)."""

    def __init__(self, max_points: int = 120) -> None:
        super().__init__()
        self._max_points = max_points
        self._download: deque[float] = deque(maxlen=max_points)
        self._upload: deque[float] = deque(maxlen=max_points)
        self.set_content_height(140)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def push_sample(self, download_bps: float, upload_bps: float) -> None:
        self._download.append(download_bps)
        self._upload.append(upload_bps)
        self.queue_draw()

    def clear(self) -> None:
        self._download.clear()
        self._upload.clear()
        self.queue_draw()

    def _draw(self, area: Gtk.DrawingArea, ctx, width: int, height: int) -> None:
        style_context = self.get_style_context()
        accent = style_context.lookup_color("accent_color")[1]
        success = style_context.lookup_color("success_color")[1]

        ctx.set_source_rgba(0, 0, 0, 0)
        ctx.paint()

        max_value = max([*self._download, *self._upload, 1.0])
        self._draw_grid(ctx, width, height)
        self._draw_series(ctx, self._download, width, height, max_value, accent)
        self._draw_series(ctx, self._upload, width, height, max_value, success)

    @staticmethod
    def _draw_grid(ctx, width: int, height: int) -> None:
        ctx.set_source_rgba(0.5, 0.5, 0.5, 0.15)
        ctx.set_line_width(1)
        for i in range(1, 4):
            y = height * i / 4
            ctx.move_to(0, y)
            ctx.line_to(width, y)
        ctx.stroke()

    def _draw_series(self, ctx, series, width, height, max_value, color: Gdk.RGBA) -> None:
        if len(series) < 2:
            return
        step = width / max(self._max_points - 1, 1)
        ctx.set_source_rgba(color.red, color.green, color.blue, 0.9)
        ctx.set_line_width(2)
        points = list(series)
        offset = self._max_points - len(points)
        for index, value in enumerate(points):
            x = (offset + index) * step
            y = height - (value / max_value) * (height - 8) - 4
            if index == 0:
                ctx.move_to(x, y)
            else:
                ctx.line_to(x, y)
        ctx.stroke_preserve()
        # Fill under the curve for a subtle area effect.
        last_x = (offset + len(points) - 1) * step
        ctx.line_to(last_x, height)
        ctx.line_to(offset * step, height)
        ctx.close_path()
        ctx.set_source_rgba(color.red, color.green, color.blue, 0.12)
        ctx.fill()
