"""Welcome / CONNECT TESLA screen."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QRadialGradient
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme
from .widgets import AnimatedButton, Spinner, label


class ConnectPage(QWidget):
    connect_clicked = Signal()
    cancel_clicked = Signal()
    settings_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 30)
        root.addStretch(3)

        self.hero = QWidget()
        hero = QVBoxLayout(self.hero)
        hero.setSpacing(0)
        hero.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        mark = QLabel("TK")
        f = QFont(theme.font_family())
        f.setPixelSize(120)
        f.setWeight(QFont.Weight.ExtraLight)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 28)
        mark.setFont(f)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.addWidget(mark)

        sub = label("TESLA  KEY", "caption")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("font-size:13px; letter-spacing:10px;")
        hero.addWidget(sub)
        hero.addSpacing(26)

        tag = label("Цифровой ключ для вашей Tesla.\nОфициальная авторизация Tesla и Fleet API.", "muted")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag.setStyleSheet("font-size:14px; line-height:150%;")
        hero.addWidget(tag)
        hero.addSpacing(40)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.connect_btn = AnimatedButton("Connect Tesla", "primary", 56)
        self.connect_btn.setFixedWidth(320)
        self.connect_btn.clicked.connect(self.connect_clicked)
        btn_row.addWidget(self.connect_btn)
        btn_row.addStretch()
        hero.addLayout(btn_row)
        hero.addSpacing(18)

        wait_row = QHBoxLayout()
        wait_row.addStretch()
        self.spinner = Spinner(22)
        self.spinner.hide()
        self.status = label("", "muted")
        wait_row.addWidget(self.spinner)
        wait_row.addSpacing(8)
        wait_row.addWidget(self.status)
        wait_row.addStretch()
        hero.addLayout(wait_row)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch()
        self.cancel_btn = AnimatedButton("Отменить", "text", 36)
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        self.cancel_btn.hide()
        cancel_row.addWidget(self.cancel_btn)
        cancel_row.addStretch()
        hero.addLayout(cancel_row)

        root.addWidget(self.hero)
        root.addStretch(4)

        foot = QHBoxLayout()
        note = label("Пароль Tesla не передаётся в TK и не сохраняется. Токены зашифрованы.", "muted")
        note.setStyleSheet(f"color:{theme.DIM}; font-size:12px;")
        settings = AnimatedButton("Настройки разработчика", "text", 34)
        settings.setMinimumWidth(280)
        settings.clicked.connect(self.settings_clicked)
        foot.addWidget(note)
        foot.addStretch()
        foot.addWidget(settings)
        root.addLayout(foot)

        self._effect = QGraphicsOpacityEffect(self.hero)
        self.hero.setGraphicsEffect(self._effect)

    def showEvent(self, e):
        super().showEvent(e)
        a = QPropertyAnimation(self._effect, b"opacity", self)
        a.setDuration(900)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def set_waiting(self, waiting: bool, text: str = ""):
        self.connect_btn.set_loading(waiting)
        self.cancel_btn.setVisible(waiting)
        self.status.setText(text)
        (self.spinner.start if waiting and text else self.spinner.stop)()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG))
        c = QPointF(self.width() / 2, self.height() * 0.42)
        g = QRadialGradient(c, max(self.width(), self.height()) * 0.55)
        g.setColorAt(0.0, QColor(255, 255, 255, 18))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), g)
