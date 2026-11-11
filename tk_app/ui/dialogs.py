"""Modal dialogs: confirmation, vehicle picker, settings."""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout,
                               QHBoxLayout, QLineEdit, QScrollArea, QVBoxLayout, QWidget)

from ..api import VehicleSummary
from ..config import REGION_LABELS, AppConfig
from . import theme
from .widgets import AnimatedButton, Card, divider, label


class _BaseDialog(QDialog):
    """Frameless rounded dialog with fade-in."""

    def __init__(self, parent=None, width: int = 440):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.card = Card()
        self.card.setStyleSheet(f"QFrame#Card{{background:{theme.SURFACE};border:1px solid {theme.BORDER_HI};"
                                f"border-radius:24px;}}")
        self.card.setFixedWidth(width)
        outer.addWidget(self.card)
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(32, 30, 32, 26)
        self.body.setSpacing(14)
        self._drag = None

    def showEvent(self, e):
        super().showEvent(e)
        self.setWindowOpacity(0.0)
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(220)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    # allow dragging the frameless dialog
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


class ConfirmDialog(_BaseDialog):
    def __init__(self, title: str, text: str, confirm: str = "Подтвердить",
                 danger: bool = False, parent=None):
        super().__init__(parent)
        self.body.addWidget(label(title, "h2"))
        self.body.addWidget(label(text, "muted", wrap=True))
        self.body.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(10)
        cancel = AnimatedButton("Отмена", "ghost", 46)
        ok = AnimatedButton(confirm, "danger" if danger else "primary", 46)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        self.body.addLayout(row)
        ok.setFocus()

    @staticmethod
    def ask(parent, title, text, confirm="Подтвердить", danger=False) -> bool:
        return ConfirmDialog(title, text, confirm, danger, parent).exec() == QDialog.DialogCode.Accepted


class _VehicleOption(AnimatedButton):
    def __init__(self, v: VehicleSummary):
        super().__init__("", "ghost", 76)
        self.v = v
        self.setCheckable(True)

    def paintEvent(self, e):
        super().paintEvent(e)
        from PySide6.QtGui import QPainter, QColor, QPen
        from .widgets import _font
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(24, 0, -24, 0)
        p.setPen(QColor("#ffffff"))
        p.setFont(_font(16))
        p.drawText(r.adjusted(0, 14, 0, -36), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.v.name)
        p.setPen(QColor(theme.MUTED))
        p.setFont(_font(11, spacing=1.5))
        masked = f"VIN ···{self.v.vin[-6:]}" if self.v.vin else ""
        p.drawText(r.adjusted(0, 40, 0, -12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, masked)
        state = {"online": "В СЕТИ", "asleep": "СПИТ", "offline": "НЕ В СЕТИ"}.get(self.v.state, self.v.state.upper())
        p.drawText(r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, state)
        if self.isChecked():
            p.setPen(QPen(QColor("#ffffff"), 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5), 37, 37)


class VehicleSelectDialog(_BaseDialog):
    def __init__(self, vehicles: list[VehicleSummary], current_vin: str = "", parent=None):
        super().__init__(parent, width=480)
        self.selected: VehicleSummary | None = None
        self.body.addWidget(label("ВЫБОР АВТОМОБИЛЯ", "caption"))
        self.body.addWidget(label("Ваши автомобили Tesla", "h2"))
        self.body.addSpacing(6)

        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.group = QButtonGroup(self)
        for v in vehicles:
            opt = _VehicleOption(v)
            self.group.addButton(opt)
            lay.addWidget(opt)
            if v.vin == current_vin or len(vehicles) == 1:
                opt.setChecked(True)
        if self.group.checkedButton() is None and self.group.buttons():
            self.group.buttons()[0].setChecked(True)
        self.group.buttonClicked.connect(lambda *_: [b.update() for b in self.group.buttons()])

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        scroll.setMaximumHeight(min(360, 90 * len(vehicles) + 10))
        scroll.setMinimumHeight(min(360, 86 * len(vehicles)))
        self.body.addWidget(scroll)
        self.body.addSpacing(6)

        row = QHBoxLayout()
        cancel = AnimatedButton("Отмена", "ghost", 46)
        ok = AnimatedButton("Выбрать", "primary", 46)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        self.body.addLayout(row)

    def _accept(self):
        btn = self.group.checkedButton()
        if btn:
            self.selected = btn.v
            self.accept()


class SettingsDialog(_BaseDialog):
    """Tesla Developer configuration. Client secret goes to Windows Credential Manager."""

    def __init__(self, config: AppConfig, client_secret: str, parent=None):
        super().__init__(parent, width=560)
        self.config = config
        self.body.addWidget(label("НАСТРОЙКИ", "caption"))
        self.body.addWidget(label("Tesla Developer", "h2"))
        self.body.addWidget(label("Данные приложения с developer.tesla.com. Пароль Tesla здесь не нужен — "
                                  "вход выполняется на сайте Tesla.", "muted", wrap=True))

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        def row(i, title, widget):
            grid.addWidget(label(title.upper(), "caption"), i * 2, 0, 1, 2)
            grid.addWidget(widget, i * 2 + 1, 0, 1, 2)

        self.client_id = QLineEdit(config.client_id)
        self.client_id.setPlaceholderText("Client ID")
        self.client_secret = QLineEdit(client_secret)
        self.client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.client_secret.setPlaceholderText("Client Secret (хранится в диспетчере учётных данных Windows)")
        self.redirect = QLineEdit(config.redirect_uri)
        self.region = QComboBox()
        for code, name in REGION_LABELS.items():
            self.region.addItem(name, code)
        self.region.setCurrentIndex(max(0, self.region.findData(config.region)))

        self.proxy_url = QLineEdit(config.proxy_url)
        self.proxy_url.setPlaceholderText("https://localhost:4443  (пусто — без прокси)")
        cert_row = QWidget()
        cl = QHBoxLayout(cert_row)
        cl.setContentsMargins(0, 0, 0, 0)
        self.proxy_cert = QLineEdit(config.proxy_ca_cert)
        self.proxy_cert.setPlaceholderText("tls-cert.pem прокси")
        browse = AnimatedButton("Обзор", "ghost", 42)
        browse.setMinimumWidth(100)
        browse.clicked.connect(self._browse)
        cl.addWidget(self.proxy_cert, 1)
        cl.addWidget(browse)

        self.domain = QLineEdit(config.partner_domain)
        self.domain.setPlaceholderText("example.com — домен с публичным ключом")
        self.confirm = QCheckBox("Подтверждать команды перед отправкой")
        self.confirm.setChecked(config.confirm_commands)

        row(0, "Client ID", self.client_id)
        row(1, "Client Secret", self.client_secret)
        row(2, "Redirect URI", self.redirect)
        row(3, "Регион Fleet API", self.region)
        row(4, "Прокси подписи команд (tesla-http-proxy)", self.proxy_url)
        row(5, "Сертификат прокси", cert_row)
        row(6, "Домен приложения", self.domain)
        form = QWidget()
        form.setLayout(grid)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form)
        scroll.setMinimumHeight(360)
        scroll.setMaximumHeight(460)
        self.body.addWidget(scroll)
        self.body.addWidget(self.confirm)

        pair = AnimatedButton("Добавить ключ в автомобиль", "ghost", 44)
        pair.clicked.connect(self._pair)
        self.body.addWidget(pair)
        self.body.addWidget(divider())

        btns = QHBoxLayout()
        cancel = AnimatedButton("Отмена", "ghost", 46)
        save = AnimatedButton("Сохранить", "primary", 46)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(save)
        self.body.addLayout(btns)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Сертификат прокси", "", "PEM (*.pem *.crt);;Все файлы (*)")
        if path:
            self.proxy_cert.setText(path)

    def _pair(self):
        domain = self.domain.text().strip().removeprefix("https://").strip("/")
        if domain:
            # Official virtual-key enrollment link; opens in the Tesla app on the phone
            webbrowser.open(f"https://tesla.com/_ak/{domain}")

    def apply(self) -> str:
        """Writes fields into config; returns the client secret for secure storage."""
        c = self.config
        c.client_id = self.client_id.text().strip()
        c.redirect_uri = self.redirect.text().strip() or "http://localhost:8765/callback"
        c.region = self.region.currentData()
        c.proxy_url = self.proxy_url.text().strip().rstrip("/")
        c.proxy_ca_cert = self.proxy_cert.text().strip()
        c.partner_domain = self.domain.text().strip().removeprefix("https://").strip("/")
        c.confirm_commands = self.confirm.isChecked()
        return self.client_secret.text().strip()
