"""
Pluggable background renderers for NodeEditorView.

BackgroundRenderer     - base class
GridBackgroundRenderer - CPU, QPainter + numpy (matches original grid)
SolidBackgroundRenderer- plain colour fill
ModernGLBackgroundRenderer - GPU via standalone moderngl context on a worker thread;
                             falls back to GridBackgroundRenderer if unavailable.
"""
from __future__ import annotations
import math

import numpy as np

from PySide6.QtGui  import QPainter, QColor, QPen, QImage
from PySide6.QtCore import QRectF, QSize, QPointF, QLineF, QThread, QMutex, QMutexLocker

from gui.theme import GRID_FINE, GRID_COARSE, BG_DARKER


# -- GLSL source ---------------------------------------------------------------

_VERT_SRC = """\
#version 330 core
in vec2 in_vert;
void main() {
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG_SRC = """\
#version 330 core
uniform vec2  u_resolution;
uniform float u_zoom;
uniform vec2  u_scene_origin;
uniform vec4  u_bg_color;
uniform vec4  u_fine_color;
uniform vec4  u_coarse_color;
uniform float u_step_fine;
uniform float u_step_coarse;
out vec4 fragColor;

float grid_factor(float coord, float step) {
    float d       = abs(mod(coord + step * 0.5, step) - step * 0.5);
    float half_px = 0.5 / u_zoom;
    return 1.0 - smoothstep(half_px, half_px * 3.0, d);
}

void main() {
    // OpenGL y=0 at bottom; Qt y=0 at top - flip.
    vec2 screen = vec2(gl_FragCoord.x, u_resolution.y - gl_FragCoord.y);
    vec2 scene  = u_scene_origin + screen / u_zoom;

    float fine   = max(grid_factor(scene.x, u_step_fine),
                       grid_factor(scene.y, u_step_fine));
    float coarse = max(grid_factor(scene.x, u_step_coarse),
                       grid_factor(scene.y, u_step_coarse));

    vec3 col = u_bg_color.rgb;
    col = mix(col, u_fine_color.rgb,   fine   * u_fine_color.a);
    col = mix(col, u_coarse_color.rgb, coarse * u_coarse_color.a);
    fragColor = vec4(col, 1.0);
}
"""


def _hex_to_glf(hex_color: str, alpha: float = 1.0) -> tuple:
    c = QColor(hex_color)
    return (c.redF(), c.greenF(), c.blueF(), alpha)

# -- Worker thread -------------------------------------------------------------

class _BGRenderWorker(QThread):
    """Renders the grid on a standalone moderngl context, independent of the main thread."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("BGRenderWorker")
        self._mutex  = QMutex()
        self._stop   = False

        self._p_width  = 0
        self._p_height = 0
        self._p_zoom   = 1.0
        self._p_ox     = 0.0
        self._p_oy     = 0.0

        self._image: QImage | None = None
        self._fresh = False
        self._params_ver = 0
        self._frame_ver  = -1

    def update_params(self, w: int, h: int, zoom: float, ox: float, oy: float) -> None:
        with QMutexLocker(self._mutex):
            if (w, h, zoom, ox, oy) != (self._p_width, self._p_height,
                                         self._p_zoom, self._p_ox, self._p_oy):
                self._params_ver += 1
            self._p_width  = w
            self._p_height = h
            self._p_zoom   = zoom
            self._p_ox     = ox
            self._p_oy     = oy

    def get_params_ver(self) -> int:
        with QMutexLocker(self._mutex):
            return self._params_ver

    def take_frame(self) -> tuple[QImage | None, int]:
        with QMutexLocker(self._mutex):
            if self._fresh and self._image is not None:
                self._fresh = False
                return self._image, self._frame_ver
        return None, -1

    def stop(self) -> None:
        self._stop = True
        self.quit()
        self.wait(2000)

    def run(self) -> None:
        try:
            import moderngl
            ctx = moderngl.create_standalone_context(require=330)
        except Exception:
            return

        try:
            prog = ctx.program(vertex_shader=_VERT_SRC, fragment_shader=_FRAG_SRC)
        except Exception:
            ctx.release()
            return

        TRIANGLES = moderngl.TRIANGLES

        # Full-screen triangle - one large triangle covers the entire clip space.
        vbo = ctx.buffer(np.array([-1.0, -1.0,  3.0, -1.0,  -1.0,  3.0], dtype="f4").tobytes())
        vao = ctx.simple_vertex_array(prog, vbo, "in_vert")

        fbo:      object | None = None
        fbo_size: tuple[int, int] = (0, 0)

        try:
            while not self._stop:
                with QMutexLocker(self._mutex):
                    w, h   = self._p_width, self._p_height
                    zoom   = self._p_zoom
                    ox, oy = self._p_ox, self._p_oy
                    ver    = self._params_ver

                if w <= 0 or h <= 0:
                    self.msleep(16)
                    continue

                if (w, h) != fbo_size:
                    if fbo is not None:
                        fbo.release()
                    fbo      = ctx.framebuffer(color_attachments=[ctx.texture((w, h), 4)])
                    fbo_size = (w, h)

                fbo.use()
                ctx.viewport = (0, 0, w, h)

                zoom = max(zoom, 1e-6)
                log_z       = math.log10(100.0 / zoom)
                exp_        = math.floor(log_z)
                f           = log_z - exp_
                step_fine   = 10.0 ** exp_
                step_coarse = step_fine * 10.0
                alpha_fine  = (1.0 - f) * 0.15

                bg = _hex_to_glf(BG_DARKER)
                fc = _hex_to_glf(GRID_FINE,   alpha_fine)
                cc = _hex_to_glf(GRID_COARSE, 0.30)

                prog["u_resolution"].value    = (w, h)
                prog["u_zoom"].value          = zoom
                prog["u_scene_origin"].value  = (ox, oy)
                prog["u_bg_color"].value      = bg
                prog["u_fine_color"].value    = fc
                prog["u_coarse_color"].value  = cc
                prog["u_step_fine"].value     = step_fine
                prog["u_step_coarse"].value   = step_coarse

                fbo.clear(*bg)
                vao.render(TRIANGLES)

                raw = fbo.read(components=4)
                arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4)
                arr = np.ascontiguousarray(np.flipud(arr))
                img = QImage(arr.data, w, h, w * 4, QImage.Format_RGBA8888).copy()

                with QMutexLocker(self._mutex):
                    self._image     = img
                    self._frame_ver = ver
                    self._fresh     = True

                self.msleep(16)

        finally:
            if fbo is not None:
                fbo.release()
            vao.release()
            vbo.release()
            prog.release()
            ctx.release()


# -- Public renderer classes ---------------------------------------------------

class BackgroundRenderer:
    """Base class. Override render() to paint the editor background."""

    def render(
        self,
        painter:      QPainter,
        scene_rect:   QRectF,
        zoom:         float,
        viewport_size: QSize | None    = None,
        scene_origin:  QPointF | None = None,
    ) -> None:
        raise NotImplementedError

    def cleanup(self) -> None:
        pass


class SolidBackgroundRenderer(BackgroundRenderer):
    def __init__(self, color: str = BG_DARKER) -> None:
        self._color = QColor(color)

    def render(self, painter, scene_rect, zoom, viewport_size=None, scene_origin=None):
        painter.fillRect(scene_rect, self._color)


class GridBackgroundRenderer(BackgroundRenderer):
    """CPU grid using QPainter + numpy. Visually identical to the original node_editor grid."""

    def render(self, painter, scene_rect, zoom, viewport_size=None, scene_origin=None):
        painter.fillRect(scene_rect, QColor(BG_DARKER))
        if zoom <= 0:
            return

        log_z       = math.log10(100.0 / zoom)
        exp         = math.floor(log_z)
        f           = log_z - exp
        step_fine   = 10.0 ** exp
        step_coarse = step_fine * 10.0

        self._draw_lines(painter, scene_rect, step_fine,   (1.0 - f) * 0.15, GRID_FINE)
        self._draw_lines(painter, scene_rect, step_coarse, 0.30,              GRID_COARSE)

    @staticmethod
    def _draw_lines(painter: QPainter, rect: QRectF, step: float, alpha: float, color_str: str):
        if alpha <= 0.01:
            return
        l = math.floor(rect.left()  / step) * step
        t = math.floor(rect.top()   / step) * step
        if int((rect.right()  - l) / step) + 1 > 100:
            return
        if int((rect.bottom() - t) / step) + 1 > 100:
            return

        c = QColor(color_str)
        c.setAlphaF(alpha)
        pen = QPen(c)
        pen.setWidthF(1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)

        lines: list[QLineF] = []
        for x in np.arange(l, rect.right()  + step, step):
            lines.append(QLineF(x, rect.top(),  x, rect.bottom()))
        for y in np.arange(t, rect.bottom() + step, step):
            lines.append(QLineF(rect.left(), y, rect.right(), y))
        if lines:
            painter.drawLines(lines)


class ModernGLBackgroundRenderer(BackgroundRenderer):
    """GPU-accelerated grid rendered on a worker thread.
    Falls back to GridBackgroundRenderer automatically if moderngl is absent or context init fails."""

    def __init__(self) -> None:
        self._fallback   = GridBackgroundRenderer()
        self._worker: _BGRenderWorker | None = None
        self._last_image: QImage | None      = None
        self._gpu_ver    = -1
        self._available  = False
        self._try_start()

    def _try_start(self) -> None:
        try:
            import moderngl  # noqa: F401
            self._worker    = _BGRenderWorker()
            self._worker.start()
            self._available = True
        except ImportError:
            self._available = False

    def render(self, painter, scene_rect, zoom, viewport_size=None, scene_origin=None):
        if not self._available or self._worker is None or viewport_size is None:
            self._fallback.render(painter, scene_rect, zoom, viewport_size, scene_origin)
            return

        w  = viewport_size.width()
        h  = viewport_size.height()
        ox = scene_origin.x() if scene_origin else 0.0
        oy = scene_origin.y() if scene_origin else 0.0

        self._worker.update_params(w, h, zoom, ox, oy)
        current_ver = self._worker.get_params_ver()

        frame, frame_ver = self._worker.take_frame()
        if frame is not None:
            self._last_image = frame
            self._gpu_ver    = frame_ver

        if self._gpu_ver < current_ver or self._last_image is None:
            # GPU frame is stale (rendered at old pan/zoom) - use CPU fallback for zero lag
            self._fallback.render(painter, scene_rect, zoom, viewport_size, scene_origin)
            return

        painter.save()
        painter.resetTransform()
        painter.drawImage(QRectF(0, 0, w, h), self._last_image)
        painter.restore()

    def cleanup(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
