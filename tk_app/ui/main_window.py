"""Main window: navigation, auth flow, vehicle refresh and command orchestration."""
from __future__ import annotations

import logging
import sys
import webbrowser

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QDialog, QMainWindow

from ..api import (AuthExpiredError, CommandProtocolRequiredError, FleetApiClient, MissingScopeError,
                   PartnerNotRegisteredError, ProxyUnavailableError, VehicleAsleepError,
                   VehicleSnapshot, VirtualKeyMissingError, WrongRegionError)
from ..auth import AuthCancelled, BrowserLogin, ReauthRequired, TokenManager
from ..config import AppConfig, resource_path
from ..secure_store import SecureStore, SecureStoreError
from ..workers import run_async
from . import theme
from .connect_page import ConnectPage
from .dashboard_page import DashboardPage
from .dialogs import ConfirmDialog, SettingsDialog, VehicleSelectDialog
from .widgets import FadeStack, Toast

log = logging.getLogger("tk")

COMMANDS = {
    "lock": ("LOCK", "Закрыть автомобиль?", "Все двери будут заблокированы.", "Автомобиль закрыт"),
    "unlock": ("UNLOCK", "Открыть автомобиль?", "Двери будут разблокированы. Убедитесь, что автомобиль "
                                                "находится под присмотром.", "Автомобиль открыт"),
    "climate_on": ("Климат", "Включить климат?", "Система начнёт подготовку салона.", "Климат включён"),
    "climate_off": ("Климат", "Выключить климат?", "Кондиционирование салона будет остановлено.", "Климат выключен"),
    "set_temp": ("Температура", "Установить температуру?", "", "Температура установлена"),
}


def app_icon() -> QIcon:
    ico = resource_path("assets/tk.ico")
    if ico.exists():
        return QIcon(str(ico))
    pm = QPixmap(256, 256)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#000"))
    p.setPen(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 56, 56)
    f = QFont(theme.font_family())
    f.setPixelSize(110)
    f.setWeight(QFont.Weight.Light)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "TK")
    p.end()
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TK — Tesla Key")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(1040, 740)
        self.resize(1200, 860)

        self.config = AppConfig.load()
        self.store = SecureStore()
        self.tokens = TokenManager(self.store, self.config)
        self.api = FleetApiClient(self.config, self.tokens)
        self._login: BrowserLogin | None = None
        self._refreshing = False

        self.stack = FadeStack()
        self.stack.setObjectName("Root")
        self.connect_page = ConnectPage()
        self.dashboard = DashboardPage()
        self.stack.addWidget(self.connect_page)
        self.stack.addWidget(self.dashboard)
        self.setCentralWidget(self.stack)
        self.toast = Toast(self.stack)

        self.connect_page.connect_clicked.connect(self.start_connect)
        self.connect_page.cancel_clicked.connect(self.cancel_connect)
        self.connect_page.settings_clicked.connect(self.open_settings)
        d = self.dashboard
        d.command_requested.connect(self.run_command)
        d.refresh_requested.connect(self.refresh)
        d.wake_requested.connect(self.wake)
        d.settings_requested.connect(self.open_settings)
        d.disconnect_requested.connect(self.disconnect_tesla)
        d.change_vehicle_requested.connect(self.load_vehicles)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)

        QTimer.singleShot(0, self._startup)

    # ================================================================ lifecycle
    def showEvent(self, e):
        super().showEvent(e)
        self._dark_titlebar()

    def closeEvent(self, e):
        if self._login:
            self._login.cancel()
        super().closeEvent(e)

    def _dark_titlebar(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            value = ctypes.c_int(1)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / pre-20H1)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
        except Exception:
            pass

    def _startup(self):
        if not self.tokens.is_authenticated:
            self.stack.setCurrentWidget(self.connect_page)
        elif self.config.selected_vin:
            self.open_dashboard()
        else:
            self.load_vehicles()

    def notify(self, text: str, kind: str = "info", ms: int = 3500):
        self.toast.show_message(text, kind, ms)

    # ================================================================ connect
    def start_connect(self):
        secret = self.store.load_client_secret()
        if not (self.config.is_configured() and secret):
            self.notify("Укажите Client ID и Client Secret вашего приложения Tesla Developer.", "muted")
            if not self.open_settings():
                return
            secret = self.store.load_client_secret()
            if not (self.config.is_configured() and secret):
                return
        self._login = BrowserLogin(self.config, secret)
        self.connect_page.set_waiting(True, "Завершите вход на сайте Tesla в браузере…")
        run_async(self._login.run, self._on_login_ok, self._on_login_error)

    def cancel_connect(self):
        if self._login:
            self._login.cancel()

    def _on_login_ok(self, tokens: dict):
        self._login = None
        try:
            self.tokens.set_tokens(tokens)
        except SecureStoreError as exc:
            self.connect_page.set_waiting(False)
            self.notify(str(exc), "error", 6000)
            return
        self.connect_page.set_waiting(True, "Получение списка автомобилей…")

        def job():
            region = None
            try:
                region = self.api.detect_region()
            except Exception as exc:  # region probe is best-effort
                log.warning("Region detection failed: %s", exc)
            return region

        def done(region):
            if region and region != self.config.region:
                log.info("Switching region %s -> %s", self.config.region, region)
                self.config.region = region
                self.config.save()
            self.load_vehicles()

        run_async(job, done, lambda exc: self.load_vehicles())

    def _on_login_error(self, exc: Exception):
        self._login = None
        self.connect_page.set_waiting(False)
        if isinstance(exc, AuthCancelled):
            return
        self._handle_error(exc)

    # ================================================================ vehicles
    def load_vehicles(self):
        if self.stack.currentWidget() is self.connect_page:
            self.connect_page.set_waiting(True, "Получение списка автомобилей…")

        def done(vehicles):
            self.connect_page.set_waiting(False)
            if not vehicles:
                self.notify("В этом аккаунте Tesla нет доступных автомобилей.", "muted", 5000)
                return
            if len(vehicles) == 1 and not self.config.selected_vin:
                chosen = vehicles[0]
            else:
                dlg = VehicleSelectDialog(vehicles, self.config.selected_vin, self)
                if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.selected:
                    if not self.config.selected_vin:
                        self.stack.fade_to(self.connect_page)
                    return
                chosen = dlg.selected
            changed = chosen.vin != self.config.selected_vin
            self.config.selected_vin = chosen.vin
            self.config.selected_name = chosen.name
            self.config.save()
            if changed:
                self.dashboard.snapshot = None
            self.open_dashboard()

        def failed(exc):
            self.connect_page.set_waiting(False)
            self._handle_error(exc)

        run_async(self.api.list_vehicles, done, failed)

    def open_dashboard(self):
        self.dashboard.show_vehicle_identity(self.config.selected_name, self.config.selected_vin)
        self.stack.fade_to(self.dashboard)
        self._update_footer()
        self.refresh()

    def _update_footer(self):
        mode = (f"Команды подписываются через прокси {self.config.proxy_url}" if self.config.uses_proxy
                else "Команды отправляются напрямую в Fleet API (только Model S/X до 2021 г.)")
        self.dashboard.set_footer(f"Tesla Fleet API · регион {self.config.region.upper()} · {mode}")

    def refresh(self):
        vin = self.config.selected_vin
        if self._refreshing or not vin or not self.tokens.is_authenticated:
            return
        self._refreshing = True
        self.dashboard.set_connection("busy", "Обновление")

        def job():
            summary = self.api.vehicle(vin)
            if summary.state != "online":
                return summary
            try:
                return self.api.vehicle_data(vin)
            except VehicleAsleepError:
                summary.state = "asleep"
                return summary

        def done(result):
            self._refreshing = False
            if isinstance(result, VehicleSnapshot):
                self.dashboard.show_snapshot(result)
                self.timer.start(max(30, self.config.auto_refresh_seconds) * 1000)
            else:
                if result.name and result.name != self.config.selected_name:
                    self.config.selected_name = result.name
                    self.config.save()
                self.dashboard.show_asleep(result.name, result.state)
                self.timer.start(5 * 60 * 1000)   # sleeping car: poll rarely, never wake it

        def failed(exc):
            self._refreshing = False
            self.dashboard.set_connection("error", "Ошибка связи")
            self._handle_error(exc, silent_network=True)

        run_async(job, done, failed)

    def wake(self):
        vin = self.config.selected_vin
        self.dashboard.wake_btn.set_loading(True)
        self.dashboard.set_connection("busy", "Пробуждение")

        def job():
            self.api.wake_up(vin)
            return self.api.vehicle_data(vin)

        def done(snap):
            self.dashboard.wake_btn.set_loading(False)
            self.dashboard.show_snapshot(snap)
            self.notify("Автомобиль на связи")

        def failed(exc):
            self.dashboard.wake_btn.set_loading(False)
            self.dashboard.set_connection("error", "Не в сети")
            self._handle_error(exc)

        run_async(job, done, failed)

    # ================================================================ commands
    def run_command(self, action: str):
        vin = self.config.selected_vin
        if not vin or action not in COMMANDS:
            return
        _, title, text, success = COMMANDS[action]
        temp = self.dashboard.target_temp
        if action == "set_temp":
            text = f"Целевая температура салона: {temp:.1f} °C."

        # UNLOCK is always confirmed; other commands follow the setting
        if action == "unlock" or self.config.confirm_commands:
            confirm_text = {"lock": "Lock", "unlock": "Unlock"}.get(action, "Подтвердить")
            if not ConfirmDialog.ask(self, title, text, confirm_text, danger=(action == "unlock")):
                if action.startswith("climate"):
                    self.dashboard.revert_climate_toggle()
                return

        fn = {
            "lock": lambda: self.api.lock(vin),
            "unlock": lambda: self.api.unlock(vin),
            "climate_on": lambda: self.api.climate_on(vin),
            "climate_off": lambda: self.api.climate_off(vin),
            "set_temp": lambda: self.api.set_temperature(vin, temp),
        }[action]

        self.dashboard.set_busy(action, True)
        self.dashboard.set_connection("busy", "Отправка команды")
        log.info("Command %s -> %s", action, vin[-6:])

        def done(_):
            self.dashboard.set_busy(action, False)
            self.notify(success)
            QTimer.singleShot(2500, self.refresh)

        def failed(exc):
            self.dashboard.set_busy(action, False)
            if action.startswith("climate"):
                self.dashboard.revert_climate_toggle()
            self.dashboard.set_connection("error", "Команда не выполнена")
            self._handle_error(exc)

        run_async(fn, done, failed)

    # ================================================================ settings / disconnect
    def open_settings(self) -> bool:
        old_region = self.config.region
        dlg = SettingsDialog(self.config, self.store.load_client_secret(), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        secret = dlg.apply()
        try:
            self.store.save_client_secret(secret)
        except SecureStoreError as exc:
            self.notify(f"Не удалось сохранить секрет: {exc}", "error", 6000)
        self.config.save()
        self._update_footer()
        if self.tokens.is_authenticated and self.config.region != old_region:
            self.notify("Регион изменён. Если запросы не проходят — переподключите Tesla.", "muted", 5000)
        else:
            self.notify("Настройки сохранены")
        return True

    def disconnect_tesla(self):
        if not ConfirmDialog.ask(self, "Отключить Tesla?",
                                 "Токены доступа будут удалены с этого компьютера. Полностью отозвать доступ "
                                 "приложения можно в настройках безопасности аккаунта Tesla.",
                                 "Disconnect", danger=True):
            return
        self._sign_out("Tesla отключена")

    def _sign_out(self, message: str, kind: str = "info"):
        self.timer.stop()
        self.tokens.clear()
        self.config.selected_vin = ""
        self.config.selected_name = ""
        self.config.save()
        self.dashboard.snapshot = None
        self.connect_page.set_waiting(False)
        self.stack.fade_to(self.connect_page)
        self.notify(message, kind, 5000)

    # ================================================================ errors
    def _handle_error(self, exc: Exception, silent_network: bool = False):
        log.error("%s: %s\n%s", type(exc).__name__, exc, getattr(exc, "__tk_traceback__", ""))
        if isinstance(exc, (ReauthRequired, AuthExpiredError)):
            self._sign_out(str(exc), "error")
        elif isinstance(exc, VirtualKeyMissingError):
            if self.config.partner_domain and ConfirmDialog.ask(
                    self, "Нужен виртуальный ключ",
                    "Автомобиль не доверяет ключу приложения TK. Откройте ссылку на телефоне с приложением "
                    "Tesla и подтвердите добавление ключа, находясь рядом с автомобилем.", "Открыть ссылку"):
                webbrowser.open(f"https://tesla.com/_ak/{self.config.partner_domain}")
            else:
                self.notify(str(exc), "error", 7000)
        elif isinstance(exc, (CommandProtocolRequiredError, ProxyUnavailableError,
                              PartnerNotRegisteredError, WrongRegionError, MissingScopeError)):
            ConfirmDialog.ask(self, "Требуется настройка", str(exc), "Понятно")
        elif silent_network and type(exc).__name__ == "NetworkError":
            self.notify(str(exc), "muted")
        else:
            self.notify(str(exc) or type(exc).__name__, "error", 6000)
