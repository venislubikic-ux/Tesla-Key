"""Custom animated widgets: buttons, control tiles, battery ring, car silhouette, toasts."""
from __future__ import annotations

import math

from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint, QPointF, QPropertyAnimation, QRectF,
                            QSize, Qt, QTimer, QVariantAnimation, Property)
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGraphicsOpacityEffect, QLabel, QPushButton,
                               QStackedWidget, QWidget)

from . import theme
from .theme import qcolor, mix

WHITE = QColor("#ffffff")
BLACK = QColor("#000000")
CLEAR = QColor(255, 255, 255, 0)


def _rpen(color, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def _font(size: int, weight=QFont.Weight.Normal, spacing: float = 0.0) -> QFont:
    f = QFont(theme.font_family())
    f.setPixelSize(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


class _HoverMixin:
    """Animated hover/press progress (0..1) for custom-painted buttons."""

    def _init_hover(self):
        self._hover = 0.0
        self._press = 0.0
        self._hover_anim = QPropertyAnimation(self, b"hover", self)
        self._hover_anim.setDuration(220)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._press_anim = QPropertyAnimation(self, b"press", self)
        self._press_anim.setDuration(140)
        self._press_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _animate(self, anim, end):
        anim.stop()
        anim.setStartValue(anim.targetObject().property(anim.propertyName().data().decode()))
        anim.setEndValue(end)
        anim.start()

    def enterEvent(self, e):
        self._animate(self._hover_anim, 1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate(self._hover_anim, 0.0)
        self._animate(self._press_anim, 0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self._animate(self._press_anim, 1.0)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._animate(self._press_anim, 0.0)
        super().mouseReleaseEvent(e)


# ======================================================================= buttons
class AnimatedButton(_HoverMixin, QPushButton):
    """Pill button. variants: primary (white), ghost (outline), danger, text."""

    def __init__(self, text: str, variant: str = "primary", height: int = 50, parent=None):
        super().__init__(text, parent)
        self.variant = variant
        self._loading = False
        self._angle = 0.0
        self._init_hover()
        self._spin = QVariantAnimation(self, startValue=0.0, endValue=360.0, duration=900, loopCount=-1)
        self._spin.valueChanged.connect(self._on_spin)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(height)
        self.setMinimumWidth(120)

    def getHover(self): return self._hover
    def setHover(self, v): self._hover = v; self.update()
    hover = Property(float, getHover, setHover)

    def getPress(self): return self._press
    def setPress(self, v): self._press = v; self.update()
    press = Property(float, getPress, setPress)

    def _on_spin(self, v):
        self._angle = v
        self.update()

    def set_loading(self, loading: bool):
        self._loading = loading
        self.setEnabled(not loading)
        (self._spin.start if loading else self._spin.stop)()
        self.update()

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(max(140, fm.horizontalAdvance(self.text()) + 70), self.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h, pr = self._hover, self._press
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        s = 2.0 * pr
        r.adjust(s, s, -s, -s)
        radius = r.height() / 2

        border = None
        if self.variant == "primary":
            bg, fg = mix(WHITE, QColor("#d4d4d4"), h), BLACK
        elif self.variant == "danger":
            bg = mix(CLEAR, qcolor(theme.DANGER, 0.12), h)
            border = mix(QColor(theme.BORDER_HI), QColor(theme.DANGER), h)
            fg = mix(WHITE, QColor(theme.DANGER), h)
        elif self.variant == "text":
            bg, fg = CLEAR, mix(QColor(theme.MUTED), WHITE, h)
        else:
            bg = mix(CLEAR, qcolor("#ffffff", 0.08), h)
            border = mix(QColor(theme.BORDER_HI), WHITE, h)
            fg = WHITE

        if not self.isEnabled() and not self._loading:
            p.setOpacity(0.35)
        p.setPen(QPen(border, 1.2) if border else Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, radius, radius)

        if self._loading:
            d = 18
            arc = QRectF(r.center().x() - d / 2, r.center().y() - d / 2, d, d)
            p.setPen(_rpen(fg, 2))
            p.drawArc(arc, int(-self._angle * 16), 100 * 16)
        else:
            p.setPen(fg)
            p.setFont(_font(12, QFont.Weight.DemiBold, 2.0))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text().upper())


# ======================================================================= icons
def draw_icon(p: QPainter, name: str, rect: QRectF, color: QColor, stroke: float = 2.0):
    p.save()
    p.setPen(QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    if name in ("lock", "unlock"):
        body = QRectF(x + w * 0.2, y + h * 0.45, w * 0.6, h * 0.45)
        p.drawRoundedRect(body, w * 0.08, w * 0.08)
        shackle = QPainterPath()
        left, right = x + w * 0.32, x + w * 0.68
        top = y + h * 0.1
        if name == "lock":
            shackle.moveTo(left, body.top())
            shackle.lineTo(left, y + h * 0.3)
            shackle.arcTo(QRectF(left, top, right - left, (right - left)), 180, -180)
            shackle.lineTo(right, body.top())
        else:
            shackle.moveTo(left, body.top())
            shackle.lineTo(left, y + h * 0.3)
            shackle.arcTo(QRectF(left, top, right - left, (right - left)), 180, -180)
            shackle.lineTo(right, y + h * 0.3)
        p.drawPath(shackle)
        p.drawLine(QPointF(x + w / 2, body.top() + body.height() * 0.35),
                   QPointF(x + w / 2, body.top() + body.height() * 0.65))
    elif name == "fan":
        c = rect.center()
        for i in range(3):
            p.save()
            p.translate(c)
            p.rotate(i * 120)
            blade = QPainterPath()
            blade.moveTo(0, 0)
            blade.cubicTo(w * 0.05, -h * 0.25, w * 0.32, -h * 0.42, w * 0.12, -h * 0.45)
            blade.cubicTo(-w * 0.1, -h * 0.45, -w * 0.12, -h * 0.2, 0, 0)
            p.drawPath(blade)
            p.restore()
        p.drawEllipse(c, w * 0.05, w * 0.05)
    elif name == "power":
        arc = rect.adjusted(w * 0.15, h * 0.18, -w * 0.15, -h * 0.12)
        p.drawArc(arc, 120 * 16, 300 * 16)
        p.drawLine(QPointF(x + w / 2, y + h * 0.08), QPointF(x + w / 2, y + h * 0.48))
    elif name == "refresh":
        arc = rect.adjusted(w * 0.18, h * 0.18, -w * 0.18, -h * 0.18)
        p.drawArc(arc, 30 * 16, 290 * 16)
        tip = QPointF(arc.right() - w * 0.04, arc.top() + h * 0.18)
        p.drawLine(tip, tip + QPointF(-w * 0.18, -h * 0.02))
        p.drawLine(tip, tip + QPointF(w * 0.02, -h * 0.18))
    elif name == "bolt":
        path = QPainterPath()
        path.moveTo(x + w * 0.58, y + h * 0.05)
        path.lineTo(x + w * 0.25, y + h * 0.55)
        path.lineTo(x + w * 0.5, y + h * 0.55)
        path.lineTo(x + w * 0.42, y + h * 0.95)
        path.lineTo(x + w * 0.75, y + h * 0.42)
        path.lineTo(x + w * 0.5, y + h * 0.42)
        path.closeSubpath()
        p.setBrush(color)
        p.drawPath(path)
    elif name == "gear":
        c = rect.center()
        p.drawEllipse(c, w * 0.16, w * 0.16)
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(QPointF(c.x() + math.cos(a) * w * 0.28, c.y() + math.sin(a) * h * 0.28),
                       QPointF(c.x() + math.cos(a) * w * 0.42, c.y() + math.sin(a) * h * 0.42))
        p.drawEllipse(c, w * 0.29, w * 0.29)
    elif name == "sun":
        c = rect.center()
        p.drawEllipse(c, w * 0.18, w * 0.18)
        for i in range(8):
            a = math.radians(i * 45)
            p.drawLine(QPointF(c.x() + math.cos(a) * w * 0.3, c.y() + math.sin(a) * h * 0.3),
                       QPointF(c.x() + math.cos(a) * w * 0.44, c.y() + math.sin(a) * h * 0.44))
    p.restore()


class IconButton(_HoverMixin, QAbstractButton):
    """Small round icon-only button."""

    def __init__(self, icon: str, tooltip: str = "", size: int = 40, parent=None, glyph: str = ""):
        super().__init__(parent)
        self.icon_name = icon
        self.glyph = glyph
        self._init_hover()
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def getHover(self): return self._hover
    def setHover(self, v): self._hover = v; self.update()
    hover = Property(float, getHover, setHover)

    def getPress(self): return self._press
    def setPress(self, v): self._press = v; self.update()
    press = Property(float, getPress, setPress)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(mix(QColor(theme.BORDER), WHITE, self._hover * 0.6), 1))
        p.setBrush(mix(CLEAR, qcolor("#ffffff", 0.08), self._hover))
        p.drawEllipse(r)
        if not self.isEnabled():
            p.setOpacity(0.35)
        if self.glyph:
            p.setPen(WHITE)
            p.setFont(_font(int(r.height() * 0.5), QFont.Weight.Light))
            p.drawText(r.adjusted(0, -2, 0, -2), Qt.AlignmentFlag.AlignCenter, self.glyph)
            return
        s = r.width() * 0.46
        draw_icon(p, self.icon_name, QRectF(r.center().x() - s / 2, r.center().y() - s / 2, s, s),
                  mix(QColor(theme.MUTED), WHITE, max(self._hover, 0.5)), 1.6)


class ControlTile(_HoverMixin, QAbstractButton):
    """Large square control (LOCK / UNLOCK / CLIMATE). `active` renders inverted (white)."""

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.icon_name = icon
        self.label = label
        self.sub = ""
        self._active = 0.0
        self._loading = False
        self._angle = 0.0
        self._init_hover()
        self._active_anim = QPropertyAnimation(self, b"activeness", self)
        self._active_anim.setDuration(350)
        self._active_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._spin = QVariantAnimation(self, startValue=0.0, endValue=360.0, duration=900, loopCount=-1)
        self._spin.valueChanged.connect(lambda v: (setattr(self, "_angle", v), self.update()))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(130, 120)

    def getHover(self): return self._hover
    def setHover(self, v): self._hover = v; self.update()
    hover = Property(float, getHover, setHover)

    def getPress(self): return self._press
    def setPress(self, v): self._press = v; self.update()
    press = Property(float, getPress, setPress)

    def getActive(self): return self._active
    def setActive(self, v): self._active = v; self.update()
    activeness = Property(float, getActive, setActive)

    def set_active(self, on: bool):
        self._active_anim.stop()
        self._active_anim.setStartValue(self._active)
        self._active_anim.setEndValue(1.0 if on else 0.0)
        self._active_anim.start()

    def set_sub(self, text: str):
        self.sub = text
        self.update()

    def set_loading(self, loading: bool):
        self._loading = loading
        self.setEnabled(not loading)
        (self._spin.start if loading else self._spin.stop)()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        s = 3.0 * self._press
        r.adjust(s, s, -s, -s)
        a = self._active
        base_bg = mix(QColor(theme.SURFACE_2), QColor("#1c1c1c"), self._hover)
        bg = mix(base_bg, WHITE, a)
        fg = mix(WHITE, BLACK, a)
        border = mix(mix(QColor(theme.BORDER), QColor(theme.BORDER_HI), self._hover), WHITE, a)
        if not self.isEnabled() and not self._loading:
            p.setOpacity(0.4)
        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 20, 20)

        icon_size = min(r.width(), r.height()) * 0.28
        icon_rect = QRectF(r.center().x() - icon_size / 2, r.top() + r.height() * 0.2, icon_size, icon_size)
        if self._loading:
            p.setPen(_rpen(fg, 2))
            p.drawArc(icon_rect.adjusted(4, 4, -4, -4), int(-self._angle * 16), 100 * 16)
        else:
            draw_icon(p, self.icon_name, icon_rect, fg, 2.0)

        p.setPen(fg)
        p.setFont(_font(12, QFont.Weight.DemiBold, 2.5))
        p.drawText(QRectF(r.left(), r.top() + r.height() * 0.58, r.width(), 20),
                   Qt.AlignmentFlag.AlignCenter, self.label)
        if self.sub:
            p.setPen(mix(QColor(theme.MUTED), QColor("#555555"), a))
            p.setFont(_font(11))
            p.drawText(QRectF(r.left(), r.top() + r.height() * 0.58 + 22, r.width(), 18),
                       Qt.AlignmentFlag.AlignCenter, self.sub)


# ======================================================================= toggle
class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(52, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._run)

    def getKnob(self): return self._pos
    def setKnob(self, v): self._pos = v; self.update()
    knob = Property(float, getKnob, setKnob)

    def _run(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_silent(self, on: bool):
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._run(on)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(mix(QColor(theme.BORDER_HI), WHITE, self._pos), 1))
        p.setBrush(mix(QColor(theme.SURFACE_2), WHITE, self._pos))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(WHITE, BLACK, self._pos))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


# ======================================================================= battery ring
class BatteryRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._target = None
        self.subtitle = ""
        self.charging = False
        self._glow = 0.0
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(1100)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuart)
        self._pulse = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1600, loopCount=-1)
        self._pulse.valueChanged.connect(lambda v: (setattr(self, "_glow", v), self.update()))
        self.setMinimumSize(190, 190)

    def getValue(self): return self._value
    def setValue(self, v): self._value = v; self.update()
    value = Property(float, getValue, setValue)

    def set_level(self, level: int | None, subtitle: str = "", charging: bool = False):
        self.subtitle = subtitle
        self.charging = charging
        (self._pulse.start if charging else self._pulse.stop)()
        self._target = level
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(float(level or 0))
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 16
        r = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        width = 9.0
        p.setPen(_rpen(QColor("#1a1a1a"), width))
        p.drawArc(r, 225 * 16, -270 * 16)
        if self._target is not None:
            span = -270 * (self._value / 100.0)
            col = WHITE if self._value > 20 else QColor(theme.DANGER)
            if self.charging:
                col = mix(WHITE, QColor("#9a9a9a"), 0.5 - 0.5 * math.cos(self._glow * 2 * math.pi))
            p.setPen(_rpen(col, width))
            p.drawArc(r, 225 * 16, int(span * 16))

        p.setPen(WHITE)
        p.setFont(_font(int(side * 0.24), QFont.Weight.ExtraLight))
        text = f"{round(self._value)}" if self._target is not None else "—"
        num_rect = QRectF(r.left(), r.center().y() - side * 0.2, r.width(), side * 0.3)
        p.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(QColor(theme.MUTED))
        p.setFont(_font(11, QFont.Weight.DemiBold, 2))
        p.drawText(QRectF(r.left(), num_rect.bottom() + 2, r.width(), 18), Qt.AlignmentFlag.AlignCenter,
                   ("% · ЗАРЯДКА" if self.charging else "% БАТАРЕЯ"))
        if self.subtitle:
            p.setPen(WHITE)
            p.setFont(_font(13))
            p.drawText(QRectF(r.left(), num_rect.bottom() + 22, r.width(), 20),
                       Qt.AlignmentFlag.AlignCenter, self.subtitle)
        if self.charging:
            s = 16
            draw_icon(p, "bolt", QRectF(r.center().x() - s / 2, num_rect.top() - s - 4, s, s), WHITE, 1.2)


# ======================================================================= car silhouette
class CarSilhouette(QWidget):
    """Generic minimalist side-profile EV drawn with QPainterPath; slides in when shown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reveal = 0.0
        self.lights_on = False
        self._anim = QPropertyAnimation(self, b"reveal", self)
        self._anim.setDuration(1200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutExpo)
        self.setMinimumSize(360, 150)

    def getReveal(self): return self._reveal
    def setReveal(self, v): self._reveal = v; self.update()
    reveal = Property(float, getReveal, setReveal)

    def play(self):
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def set_lights(self, on: bool):
        self.lights_on = on
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        scale = min(w / 104.0, h / 40.0)
        ox = (w - 104 * scale) / 2 - (1 - self._reveal) * 60
        oy = (h - 40 * scale) / 2
        p.setOpacity(self._reveal)

        # floor reflection
        floor_y = oy + 34.2 * scale
        g = QLinearGradient(ox, 0, ox + 104 * scale, 0)
        g.setColorAt(0.0, qcolor("#ffffff", 0.0))
        g.setColorAt(0.5, qcolor("#ffffff", 0.25))
        g.setColorAt(1.0, qcolor("#ffffff", 0.0))
        p.setPen(QPen(g, 1))
        p.drawLine(QPointF(ox, floor_y), QPointF(ox + 104 * scale, floor_y))
        shadow = QRadialGradient(QPointF(ox + 52 * scale, floor_y), 46 * scale)
        shadow.setColorAt(0, qcolor("#ffffff", 0.06))
        shadow.setColorAt(1, qcolor("#ffffff", 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shadow)
        p.drawEllipse(QPointF(ox + 52 * scale, floor_y), 46 * scale, 3 * scale)

        p.translate(ox, oy)
        p.scale(scale, scale)

        body = QPainterPath()
        body.moveTo(9, 30)
        body.cubicTo(5, 30, 3.5, 27.5, 4, 24.5)
        body.cubicTo(4.5, 22, 6, 20.5, 9, 19.8)
        body.cubicTo(18, 17.5, 26, 15.5, 34, 11.5)
        body.cubicTo(42, 7.6, 52, 6.8, 60, 7.6)
        body.cubicTo(67, 8.4, 72, 11.5, 78, 15.8)
        body.cubicTo(86, 17, 93, 18, 97, 20.5)
        body.cubicTo(99.5, 22.5, 100, 26.5, 98.5, 28.6)
        body.cubicTo(97.5, 29.8, 96, 30, 94, 30)
        body.lineTo(87, 30)
        body.arcTo(QRectF(71, 21, 16, 16), 0, 180)
        body.lineTo(31, 30)
        body.arcTo(QRectF(15, 21, 16, 16), 0, 180)
        body.closeSubpath()

        fill = QLinearGradient(0, 6, 0, 31)
        fill.setColorAt(0, qcolor("#ffffff", 0.10))
        fill.setColorAt(1, qcolor("#ffffff", 0.01))
        p.setBrush(fill)
        p.setPen(QPen(qcolor("#ffffff", 0.9), 0.45))
        p.drawPath(body)

        glass = QPainterPath()
        glass.moveTo(30, 15.4)
        glass.cubicTo(38, 10, 48, 8.6, 58, 9.2)
        glass.cubicTo(65, 9.8, 70, 12.4, 74, 15.6)
        glass.lineTo(30, 15.4)
        p.setBrush(qcolor("#ffffff", 0.05))
        p.setPen(QPen(qcolor("#ffffff", 0.55), 0.35))
        p.drawPath(glass)
        p.drawLine(QPointF(53, 9.0), QPointF(53, 15.5))       # B-pillar
        p.setPen(QPen(qcolor("#ffffff", 0.25), 0.3))
        p.drawLine(QPointF(30, 21.5), QPointF(92, 21.5))      # character line
        p.drawLine(QPointF(53, 15.5), QPointF(53, 28.0))      # door seam

        for cx in (23, 79):
            p.setPen(QPen(qcolor("#ffffff", 0.9), 0.45))
            p.setBrush(QColor("#050505"))
            p.drawEllipse(QPointF(cx, 29), 6.6, 6.6)
            p.setPen(QPen(qcolor("#ffffff", 0.35), 0.3))
            p.drawEllipse(QPointF(cx, 29), 4.2, 4.2)
            for i in range(5):
                a = math.radians(i * 72 - 90)
                p.drawLine(QPointF(cx + math.cos(a) * 1.2, 29 + math.sin(a) * 1.2),
                           QPointF(cx + math.cos(a) * 4.0, 29 + math.sin(a) * 4.0))

        # light bars
        lit = 1.0 if self.lights_on else 0.35
        p.setPen(_rpen(qcolor("#ffffff", lit), 0.9))
        p.drawLine(QPointF(93.5, 20.2), QPointF(97.5, 21.6))
        p.setPen(_rpen(qcolor(theme.DANGER, 0.9 if self.lights_on else 0.45), 0.9))
        p.drawLine(QPointF(5.2, 21.6), QPointF(8.6, 20.4))
        if self.lights_on:
            beam = QRadialGradient(QPointF(98, 21), 10)
            beam.setColorAt(0, qcolor("#ffffff", 0.25))
            beam.setColorAt(1, qcolor("#ffffff", 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(beam)
            p.drawEllipse(QPointF(98, 21), 10, 5)


# ======================================================================= misc
class PulseDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.color = QColor(theme.DIM)
        self._t = 0.0
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1800, loopCount=-1)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_t", v), self.update()))
        self.setFixedSize(18, 18)

    def set_state(self, color: str, pulsing: bool):
        self.color = QColor(color)
        (self._anim.start if pulsing else self._anim.stop)()
        if not pulsing:
            self._t = 0.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if self._anim.state() == QVariantAnimation.State.Running:
            ring = QColor(self.color)
            ring.setAlphaF(0.5 * (1 - self._t))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ring)
            p.drawEllipse(c, 3 + 6 * self._t, 3 + 6 * self._t)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(c, 3.5, 3.5)


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")


def divider() -> QFrame:
    f = QFrame()
    f.setObjectName("Divider")
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{theme.BORDER}; border:none;")
    return f


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


class FadeStack(QStackedWidget):
    """QStackedWidget with a fade + slight rise transition."""

    def fade_to(self, widget: QWidget):
        if widget is self.currentWidget():
            return
        self.setCurrentWidget(widget)
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(420)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


class Toast(QLabel):
    """Bottom-centered transient message."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.hide()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self._fade_out)
        self._anims: QParallelAnimationGroup | None = None

    def show_message(self, text: str, kind: str = "info", ms: int = 3500):
        styles = {
            "info": "background:#ffffff; color:#000000;",
            "error": f"background:#1a0a09; color:#ffffff; border:1px solid {theme.DANGER};",
            "muted": f"background:{theme.SURFACE_2}; color:#ffffff; border:1px solid {theme.BORDER_HI};",
        }
        self.setStyleSheet(f"QLabel{{{styles.get(kind, styles['info'])} border-radius:18px;"
                           f"padding:12px 22px; font-size:13px; font-weight:500;}}")
        self.setText(text)
        par = self.parentWidget()
        self.setMaximumWidth(min(560, par.width() - 60))
        self.adjustSize()
        x = (par.width() - self.width()) // 2
        y_end = par.height() - self.height() - 36
        self.raise_()
        self.show()

        grp = QParallelAnimationGroup(self)
        a1 = QPropertyAnimation(self._effect, b"opacity")
        a1.setDuration(260)
        a1.setStartValue(0.0)
        a1.setEndValue(1.0)
        a2 = QPropertyAnimation(self, b"pos")
        a2.setDuration(360)
        a2.setEasingCurve(QEasingCurve.Type.OutCubic)
        a2.setStartValue(QPoint(x, y_end + 24))
        a2.setEndValue(QPoint(x, y_end))
        grp.addAnimation(a1)
        grp.addAnimation(a2)
        grp.start(QParallelAnimationGroup.DeletionPolicy.DeleteWhenStopped)
        self._timer.start(ms)

    def _fade_out(self):
        a = QPropertyAnimation(self._effect, b"opacity", self)
        a.setDuration(300)
        a.setStartValue(1.0)
        a.setEndValue(0.0)
        a.finished.connect(self.hide)
        a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


class Spinner(QWidget):
    def __init__(self, size: int = 28, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._a = 0.0
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=360.0, duration=900, loopCount=-1)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_a", v), self.update()))

    def start(self):
        self._anim.start()
        self.show()

    def stop(self):
        self._anim.stop()
        self.hide()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        p.setPen(QPen(QColor("#1f1f1f"), 2.2))
        p.drawEllipse(r)
        p.setPen(_rpen(WHITE, 2.2))
        p.drawArc(r, int(-self._a * 16), 90 * 16)
