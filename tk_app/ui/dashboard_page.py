"""Main screen: connected vehicle card, battery, controls, climate, status."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from ..api import VehicleSnapshot
from . import theme
from .widgets import (AnimatedButton, BatteryRing, Card, CarSilhouette, ControlTile, IconButton, PulseDot,
                      ToggleSwitch, divider, label)

CHARGING_STATES = {
    "Charging": "Идёт зарядка", "Complete": "Зарядка завершена", "Disconnected": "Кабель не подключён",
    "Stopped": "Зарядка остановлена", "NoPower": "Нет питания", "Starting": "Начало зарядки",
}


class _StatusRow(QWidget):
    def __init__(self, title: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 8)
        self.title = label(title, "muted")
        self.value = label("—", "value")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.title)
        lay.addStretch()
        lay.addWidget(self.value)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set(self, text: str, warn: bool = False):
        self.value.setText(text)
        self.value.setStyleSheet(f"color:{theme.DANGER};" if warn else "")


class DashboardPage(QWidget):
    command_requested = Signal(str)            # lock | unlock | climate_on | climate_off | set_temp
    refresh_requested = Signal()
    wake_requested = Signal()
    settings_requested = Signal()
    disconnect_requested = Signal()
    change_vehicle_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot: VehicleSnapshot | None = None
        self.target_temp = 21.0

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 26, 36, 20)
        root.setSpacing(18)

        # ---------- top bar
        top = QHBoxLayout()
        mark = QLabel("TK")
        f = QFont(theme.font_family())
        f.setPixelSize(26)
        f.setWeight(QFont.Weight.Light)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 8)
        mark.setFont(f)
        top.addWidget(mark)
        top.addSpacing(18)
        self.dot = PulseDot()
        self.conn_label = label("ПОДКЛЮЧЕНИЕ…", "caption")
        top.addWidget(self.dot)
        top.addWidget(self.conn_label)
        top.addStretch()
        self.refresh_btn = IconButton("refresh", "Обновить")
        self.refresh_btn.clicked.connect(self.refresh_requested)
        settings_btn = IconButton("gear", "Настройки")
        settings_btn.clicked.connect(self.settings_requested)
        disc = AnimatedButton("Disconnect Tesla", "danger", 40)
        disc.setMinimumWidth(190)
        disc.clicked.connect(self.disconnect_requested)
        top.addWidget(self.refresh_btn)
        top.addSpacing(6)
        top.addWidget(settings_btn)
        top.addSpacing(12)
        top.addWidget(disc)
        root.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        scroll.setWidget(content)
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 4, 0)
        grid.setSpacing(18)
        root.addWidget(scroll, 1)

        # ---------- hero card
        hero = Card()
        hl = QGridLayout(hero)
        hl.setContentsMargins(34, 30, 34, 28)
        hl.setHorizontalSpacing(30)
        left = QVBoxLayout()
        left.setSpacing(4)
        self.model_lbl = label("TESLA", "caption")
        self.name_lbl = label("—", "h1")
        self.state_lbl = label("", "muted")
        left.addWidget(self.model_lbl)
        left.addWidget(self.name_lbl)
        left.addWidget(self.state_lbl)
        self.car = CarSilhouette()
        self.car.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left.addWidget(self.car, 1)
        chips = QHBoxLayout()
        self.vin_lbl = label("", "caption")
        self.sw_lbl = label("", "caption")
        chips.addWidget(self.vin_lbl)
        chips.addSpacing(24)
        chips.addWidget(self.sw_lbl)
        chips.addStretch()
        self.change_btn = AnimatedButton("Сменить авто", "text", 32)
        self.change_btn.clicked.connect(self.change_vehicle_requested)
        chips.addWidget(self.change_btn)
        left.addLayout(chips)
        hl.addLayout(left, 0, 0)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.battery = BatteryRing()
        self.battery.setFixedSize(230, 230)
        right.addWidget(self.battery, 0, Qt.AlignmentFlag.AlignHCenter)
        self.charge_lbl = label("", "muted")
        self.charge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.charge_lbl)
        self.wake_btn = AnimatedButton("Разбудить", "primary", 42)
        self.wake_btn.setFixedWidth(200)
        self.wake_btn.clicked.connect(self.wake_requested)
        self.wake_btn.hide()
        right.addSpacing(8)
        right.addWidget(self.wake_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        hl.addLayout(right, 0, 1)
        hl.setColumnStretch(0, 3)
        hl.setColumnStretch(1, 2)
        hero.setMinimumHeight(330)
        grid.addWidget(hero, 0, 0, 1, 2)

        # ---------- controls
        controls = Card()
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(26, 24, 26, 26)
        cl.addWidget(label("УПРАВЛЕНИЕ", "caption"))
        cl.addSpacing(8)
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        self.lock_tile = ControlTile("lock", "LOCK")
        self.unlock_tile = ControlTile("unlock", "UNLOCK")
        self.lock_tile.clicked.connect(lambda: self.command_requested.emit("lock"))
        self.unlock_tile.clicked.connect(lambda: self.command_requested.emit("unlock"))
        tiles.addWidget(self.lock_tile)
        tiles.addWidget(self.unlock_tile)
        cl.addLayout(tiles, 1)
        grid.addWidget(controls, 1, 0)

        # ---------- climate
        climate = Card()
        kl = QVBoxLayout(climate)
        kl.setContentsMargins(26, 24, 26, 26)
        head = QHBoxLayout()
        head.addWidget(label("КЛИМАТ", "caption"))
        head.addStretch()
        self.climate_state = label("ВЫКЛ", "caption")
        head.addWidget(self.climate_state)
        head.addSpacing(10)
        self.climate_toggle = ToggleSwitch()
        self.climate_toggle.toggled.connect(self._on_climate_toggle)
        head.addWidget(self.climate_toggle)
        kl.addLayout(head)
        kl.addSpacing(6)

        temps = QHBoxLayout()
        self.minus = IconButton("", "−0.5°", 46, glyph="−")
        self.plus = IconButton("", "+0.5°", 46, glyph="+")
        self.temp_lbl = label("21.0°", "big")
        self.temp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.minus.clicked.connect(lambda: self._step(-0.5))
        self.plus.clicked.connect(lambda: self._step(+0.5))
        temps.addWidget(self.minus)
        temps.addWidget(self.temp_lbl, 1)
        temps.addWidget(self.plus)
        kl.addLayout(temps)

        io = QHBoxLayout()
        self.inside_lbl = label("Салон —", "muted")
        self.outside_lbl = label("Снаружи —", "muted")
        io.addWidget(self.inside_lbl)
        io.addStretch()
        io.addWidget(self.outside_lbl)
        kl.addLayout(io)
        kl.addSpacing(6)
        self.apply_temp_btn = AnimatedButton("Установить температуру", "ghost", 44)
        self.apply_temp_btn.clicked.connect(lambda: self.command_requested.emit("set_temp"))
        kl.addWidget(self.apply_temp_btn)
        grid.addWidget(climate, 1, 1)

        # ---------- status
        status = Card()
        sl = QVBoxLayout(status)
        sl.setContentsMargins(26, 22, 26, 18)
        sl.addWidget(label("СОСТОЯНИЕ АВТОМОБИЛЯ", "caption"))
        sl.addSpacing(4)
        cols = QHBoxLayout()
        cols.setSpacing(40)
        c1, c2 = QVBoxLayout(), QVBoxLayout()
        c1.setSpacing(0)
        c2.setSpacing(0)
        self.rows = {}
        for i, (key, title) in enumerate([
            ("locks", "Замки"), ("doors", "Двери"), ("windows", "Окна"), ("trunks", "Багажник / фрунк"),
            ("sentry", "Режим охраны"), ("odometer", "Пробег"), ("charge_limit", "Лимит заряда"),
            ("software", "Версия ПО"),
        ]):
            row = _StatusRow(title)
            self.rows[key] = row
            col = c1 if i < 4 else c2
            if col.count():
                col.addWidget(divider())
            col.addWidget(row)
        cols.addLayout(c1, 1)
        cols.addLayout(c2, 1)
        sl.addLayout(cols)
        grid.addWidget(status, 2, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        filler = QWidget()
        filler.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        grid.addWidget(filler, 3, 0, 1, 2)
        grid.setRowStretch(3, 1)

        self.footer = label("", "muted")
        self.footer.setStyleSheet(f"color:{theme.DIM}; font-size:11px;")
        root.addWidget(self.footer)

        self._busy: set[str] = set()
        self.set_controls_enabled(False)

    # ----------------------------------------------------------------- helpers
    def _step(self, delta: float):
        lo = self.snapshot.min_temp if self.snapshot else 15.0
        hi = self.snapshot.max_temp if self.snapshot else 28.0
        self.target_temp = max(lo, min(hi, round((self.target_temp + delta) * 2) / 2))
        self.temp_lbl.setText(f"{self.target_temp:.1f}°")

    def _on_climate_toggle(self, on: bool):
        self.command_requested.emit("climate_on" if on else "climate_off")

    def set_controls_enabled(self, enabled: bool):
        for w in (self.lock_tile, self.unlock_tile, self.climate_toggle, self.minus, self.plus,
                  self.apply_temp_btn):
            if w is self.lock_tile and "lock" in self._busy:
                continue
            if w is self.unlock_tile and "unlock" in self._busy:
                continue
            w.setEnabled(enabled)

    def set_busy(self, action: str, busy: bool):
        (self._busy.add if busy else self._busy.discard)(action)
        if action == "lock":
            self.lock_tile.set_loading(busy)
        elif action == "unlock":
            self.unlock_tile.set_loading(busy)
        elif action in ("climate_on", "climate_off"):
            self.climate_toggle.setEnabled(not busy)
        elif action == "set_temp":
            self.apply_temp_btn.set_loading(busy)
        if not busy:
            self.set_controls_enabled(True)

    def revert_climate_toggle(self):
        on = bool(self.snapshot and self.snapshot.climate_on)
        self.climate_toggle.set_silent(on)

    def set_connection(self, state: str, text: str):
        colors = {"online": ("#ffffff", True), "asleep": (theme.MUTED, False),
                  "busy": ("#ffffff", True), "error": (theme.DANGER, False), "offline": (theme.DIM, False)}
        color, pulse = colors.get(state, (theme.DIM, False))
        self.dot.set_state(color, pulse)
        self.conn_label.setText(text.upper())

    # ----------------------------------------------------------------- data
    def show_vehicle_identity(self, name: str, vin: str):
        self.name_lbl.setText(name or "Tesla")
        self.vin_lbl.setText(f"VIN ···{vin[-6:]}" if vin else "")
        self.car.play()

    def show_asleep(self, name: str, state: str):
        self.name_lbl.setText(name or self.name_lbl.text())
        txt = "Автомобиль спит — данные не запрашиваются, чтобы не расходовать заряд" \
            if state == "asleep" else "Автомобиль не в сети"
        self.state_lbl.setText(txt)
        self.wake_btn.setVisible(True)
        self.set_connection("asleep" if state == "asleep" else "offline",
                            "Спит" if state == "asleep" else "Не в сети")
        # Commands still work: TK will wake the car before sending them
        self.set_controls_enabled(True)

    def show_snapshot(self, s: VehicleSnapshot):
        first = self.snapshot is None
        self.snapshot = s
        self.wake_btn.hide()
        self.model_lbl.setText(s.model.upper() + (f"  ·  {s.color.upper()}" if s.color else ""))
        self.name_lbl.setText(s.name)
        self.vin_lbl.setText(f"VIN ···{s.vin[-6:]}" if s.vin else "")
        self.sw_lbl.setText(f"ПО {s.software}" if s.software else "")
        self.state_lbl.setText("В сети · обновлено " + time.strftime("%H:%M", time.localtime(s.updated_at)))
        self.set_connection("online", "Подключено")
        if first:
            self.car.play()

        rng = f"{s.battery_range:.0f} {s.distance_unit}" if s.battery_range is not None else ""
        charging = s.charging_state == "Charging"
        self.battery.set_level(s.battery_level, rng, charging)
        parts = [CHARGING_STATES.get(s.charging_state, s.charging_state)] if s.charging_state else []
        if charging and s.minutes_to_full:
            parts.append(f"до полного {s.minutes_to_full // 60} ч {s.minutes_to_full % 60} мин")
        if charging and s.charger_power:
            parts.append(f"{s.charger_power} кВт")
        self.charge_lbl.setText(" · ".join(parts))

        self.lock_tile.set_active(bool(s.locked))
        self.unlock_tile.set_active(s.locked is False)
        self.lock_tile.set_sub("Закрыт" if s.locked else "")
        self.unlock_tile.set_sub("Открыт" if s.locked is False else "")
        self.car.set_lights(s.locked is False)

        self.climate_toggle.set_silent(bool(s.climate_on))
        self.climate_state.setText("ВКЛ" if s.climate_on else "ВЫКЛ")
        if s.driver_temp is not None and "set_temp" not in self._busy:
            self.target_temp = float(s.driver_temp)
            self.temp_lbl.setText(f"{self.target_temp:.1f}°")
        self.inside_lbl.setText(f"Салон {s.inside_temp:.0f}°" if s.inside_temp is not None else "Салон —")
        self.outside_lbl.setText(f"Снаружи {s.outside_temp:.0f}°" if s.outside_temp is not None else "Снаружи —")

        r = self.rows
        r["locks"].set("Закрыты" if s.locked else ("Открыты" if s.locked is False else "—"), s.locked is False)
        r["doors"].set(", ".join(s.open_doors) if s.open_doors else "Закрыты", bool(s.open_doors))
        r["windows"].set(", ".join(s.open_windows) if s.open_windows else "Закрыты", bool(s.open_windows))
        trunks = [n for n, o in (("Фрунк", s.frunk_open), ("Багажник", s.trunk_open)) if o]
        r["trunks"].set(", ".join(trunks) + " открыт" if trunks else "Закрыты", bool(trunks))
        r["sentry"].set("Включён" if s.sentry else ("Выключен" if s.sentry is False else "—"))
        r["odometer"].set(f"{s.odometer:,.0f} {s.distance_unit}".replace(",", " ") if s.odometer else "—")
        r["charge_limit"].set(f"{s.charge_limit}%" if s.charge_limit else "—")
        r["software"].set(s.software or "—")
        self.set_controls_enabled(True)

    def set_footer(self, text: str):
        self.footer.setText(text)
