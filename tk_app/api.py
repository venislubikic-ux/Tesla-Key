"""Client for the official Tesla Fleet API.

Reads (vehicle list, vehicle_data, wake_up) go straight to the regional Fleet API.
Commands go through Tesla's official `tesla-http-proxy` (Vehicle Command Protocol),
which signs them with the partner private key. Without the proxy, commands are sent
as plain REST — Tesla accepts that only for pre-2021 Model S/X.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

import requests

from .auth import TokenManager
from .config import REGION_BASE_URLS, AppConfig

HTTP_TIMEOUT = 25
VEHICLE_DATA_ENDPOINTS = "charge_state;climate_state;vehicle_state;vehicle_config;gui_settings"

MODEL_NAMES = {
    "model3": "Model 3", "modely": "Model Y", "models": "Model S", "models2": "Model S",
    "modelx": "Model X", "cybertruck": "Cybertruck", "lychee": "Model S", "tamarind": "Model X",
}


# ---------------------------------------------------------------- errors
class TeslaApiError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class AuthExpiredError(TeslaApiError): pass
class VehicleAsleepError(TeslaApiError): pass
class VehicleOfflineError(TeslaApiError): pass
class WrongRegionError(TeslaApiError): pass
class RateLimitedError(TeslaApiError): pass
class CommandProtocolRequiredError(TeslaApiError): pass
class VirtualKeyMissingError(TeslaApiError): pass
class PartnerNotRegisteredError(TeslaApiError): pass
class MissingScopeError(TeslaApiError): pass
class ProxyUnavailableError(TeslaApiError): pass
class CommandFailedError(TeslaApiError): pass
class NetworkError(TeslaApiError): pass


# ---------------------------------------------------------------- models
@dataclass
class VehicleSummary:
    vin: str
    name: str
    state: str
    vehicle_id: int | None = None

    @classmethod
    def from_api(cls, d: dict) -> "VehicleSummary":
        return cls(vin=d.get("vin", ""), name=d.get("display_name") or "Tesla",
                   state=d.get("state", "unknown"), vehicle_id=d.get("id"))


@dataclass
class VehicleSnapshot:
    vin: str
    name: str = "Tesla"
    model: str = "Tesla"
    state: str = "unknown"
    color: str = ""
    battery_level: int | None = None
    battery_range: float | None = None      # in display units
    distance_unit: str = "km"
    charging_state: str = ""
    charge_limit: int | None = None
    minutes_to_full: int | None = None
    charger_power: float | None = None
    locked: bool | None = None
    sentry: bool | None = None
    odometer: float | None = None
    software: str = ""
    inside_temp: float | None = None
    outside_temp: float | None = None
    climate_on: bool | None = None
    driver_temp: float | None = None
    min_temp: float = 15.0
    max_temp: float = 28.0
    open_doors: list[str] = field(default_factory=list)
    open_windows: list[str] = field(default_factory=list)
    frunk_open: bool = False
    trunk_open: bool = False
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def from_vehicle_data(cls, d: dict) -> "VehicleSnapshot":
        cs, cl = d.get("charge_state") or {}, d.get("climate_state") or {}
        vs, vc = d.get("vehicle_state") or {}, d.get("vehicle_config") or {}
        gui = d.get("gui_settings") or {}
        km = (gui.get("gui_distance_units") or "km/hr").startswith("km")
        conv = 1.609344 if km else 1.0          # Fleet API reports miles

        def miles(v):
            return round(v * conv, 1) if isinstance(v, (int, float)) else None

        doors = {"df": "Водит. дверь", "pf": "Пассаж. дверь", "dr": "Задняя левая", "pr": "Задняя правая"}
        windows = {"fd_window": "Окно водит.", "fp_window": "Окно пассаж.",
                   "rd_window": "Окно зад. лев.", "rp_window": "Окно зад. прав."}
        car_type = (vc.get("car_type") or "").lower()
        ttf = cs.get("time_to_full_charge")

        return cls(
            vin=d.get("vin", ""),
            name=vs.get("vehicle_name") or d.get("display_name") or "Tesla",
            model=MODEL_NAMES.get(car_type, car_type.title() or "Tesla"),
            state=d.get("state", "online"),
            color=vc.get("exterior_color") or "",
            battery_level=cs.get("battery_level"),
            battery_range=miles(cs.get("battery_range")),
            distance_unit="km" if km else "mi",
            charging_state=cs.get("charging_state") or "",
            charge_limit=cs.get("charge_limit_soc"),
            minutes_to_full=int(ttf * 60) if isinstance(ttf, (int, float)) and ttf > 0 else None,
            charger_power=cs.get("charger_power"),
            locked=vs.get("locked"),
            sentry=vs.get("sentry_mode"),
            odometer=miles(vs.get("odometer")),
            software=(vs.get("car_version") or "").split(" ")[0],
            inside_temp=cl.get("inside_temp"),
            outside_temp=cl.get("outside_temp"),
            climate_on=cl.get("is_climate_on"),
            driver_temp=cl.get("driver_temp_setting"),
            min_temp=cl.get("min_avail_temp") or 15.0,
            max_temp=cl.get("max_avail_temp") or 28.0,
            open_doors=[label for k, label in doors.items() if vs.get(k)],
            open_windows=[label for k, label in windows.items() if vs.get(k)],
            frunk_open=bool(vs.get("ft")),
            trunk_open=bool(vs.get("rt")),
        )


# ---------------------------------------------------------------- client
class FleetApiClient:
    def __init__(self, config: AppConfig, tokens: TokenManager):
        self.config = config
        self.tokens = tokens
        self._local = threading.local()

    # -- plumbing --
    def _session(self) -> requests.Session:
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers["User-Agent"] = "TK-TeslaKey/1.0"
            self._local.session = s
        return s

    def _request(self, method: str, path: str, *, base: str | None = None, json: dict | None = None,
                 query: str = "", verify: bool | str = True, _retry_auth: bool = True):
        url = (base or self.config.fleet_base_url).rstrip("/") + path + (f"?{query}" if query else "")
        headers = {"Authorization": f"Bearer {self.tokens.access_token()}"}
        via_proxy = base is not None and base != self.config.fleet_base_url
        try:
            r = self._session().request(method, url, json=json, headers=headers,
                                        timeout=HTTP_TIMEOUT, verify=verify)
        except requests.exceptions.SSLError as exc:
            if via_proxy:
                raise ProxyUnavailableError(
                    "TLS-сертификат прокси не принят. Укажите файл сертификата прокси (tls-cert.pem) в настройках.") from exc
            raise NetworkError(f"Ошибка защищённого соединения: {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            if via_proxy:
                raise ProxyUnavailableError(
                    f"Прокси подписи команд не отвечает ({base}). Запустите tesla-http-proxy.") from exc
            raise NetworkError("Нет подключения к интернету или серверы Tesla недоступны.") from exc
        except requests.RequestException as exc:
            raise NetworkError(f"Сетевая ошибка: {exc}") from exc

        if r.status_code == 401 and _retry_auth:
            self.tokens.force_refresh()
            return self._request(method, path, base=base, json=json, query=query,
                                 verify=verify, _retry_auth=False)
        return self._handle(r)

    @staticmethod
    def _handle(r: requests.Response):
        try:
            data = r.json()
        except ValueError:
            data = None
        if r.status_code == 200 and isinstance(data, dict):
            return data.get("response", data)

        msg = ""
        if isinstance(data, dict):
            msg = data.get("error_description") or data.get("error") or data.get("message") or ""
            if isinstance(data.get("response"), dict) and not msg:
                msg = data["response"].get("reason", "")
        msg = msg or (r.text or "").strip()[:300] or f"HTTP {r.status_code}"
        low = msg.lower()
        code = r.status_code

        if "public key" in low or "not paired" in low or "unknown key" in low or "keychain" in low:
            raise VirtualKeyMissingError(
                "Виртуальный ключ TK не добавлен в автомобиль. Откройте «Настройки → Добавить ключ в автомобиль».", code)
        if "vehicle command protocol" in low:
            raise CommandProtocolRequiredError(
                "Автомобиль принимает только подписанные команды. Запустите tesla-http-proxy и укажите его в настройках.", code)
        if code == 401:
            raise AuthExpiredError("Сессия Tesla истекла. Подключите автомобиль снова.", code)
        if code == 403 and ("scope" in low or "unauthorized" in low or "missing" in low):
            raise MissingScopeError(f"Недостаточно прав доступа: {msg}", code)
        if code == 408 or "asleep" in low or "offline or asleep" in low:
            raise VehicleAsleepError("Автомобиль спит.", code)
        if code == 412 or "must be registered" in low or "partner" in low and "register" in low:
            raise PartnerNotRegisteredError(
                "Приложение не зарегистрировано в регионе Fleet API. Выполните tools/register_partner.py.", code)
        if code == 421:
            raise WrongRegionError("Аккаунт относится к другому региону Fleet API. Смените регион в настройках.", code)
        if code == 429:
            retry = r.headers.get("Retry-After", "")
            raise RateLimitedError(f"Слишком много запросов. Повторите {('через ' + retry + ' с') if retry else 'позже'}.", code)
        if code in (502, 503, 504):
            raise VehicleOfflineError("Автомобиль или серверы Tesla временно недоступны.", code)
        raise TeslaApiError(f"Ошибка Tesla API ({code}): {msg}", code)

    # -- account / region --
    def user_region(self) -> dict:
        return self._request("GET", "/api/1/users/region")

    def detect_region(self) -> str | None:
        """Returns region code (eu/na/cn) reported by Tesla for this account, if determinable."""
        try:
            info = self.user_region()
        except WrongRegionError:
            for region, base in REGION_BASE_URLS.items():
                if region == self.config.region:
                    continue
                try:
                    info = self._request("GET", "/api/1/users/region", base=base)
                    break
                except TeslaApiError:
                    continue
            else:
                return None
        base = (info or {}).get("fleet_api_base_url", "")
        for region, url in REGION_BASE_URLS.items():
            if url == base.rstrip("/"):
                return region
        return (info or {}).get("region") or None

    # -- vehicles --
    def list_vehicles(self) -> list[VehicleSummary]:
        data = self._request("GET", "/api/1/vehicles")
        return [VehicleSummary.from_api(v) for v in (data or [])]

    def vehicle(self, vin: str) -> VehicleSummary:
        return VehicleSummary.from_api(self._request("GET", f"/api/1/vehicles/{vin}"))

    def vehicle_data(self, vin: str) -> VehicleSnapshot:
        data = self._request("GET", f"/api/1/vehicles/{vin}/vehicle_data",
                             query=f"endpoints={VEHICLE_DATA_ENDPOINTS}")
        snap = VehicleSnapshot.from_vehicle_data(data)
        snap.vin = snap.vin or vin
        return snap

    def wake_up(self, vin: str, timeout: float = 60) -> None:
        deadline = time.monotonic() + timeout
        self._request("POST", f"/api/1/vehicles/{vin}/wake_up")
        while time.monotonic() < deadline:
            if self.vehicle(vin).state == "online":
                return
            time.sleep(3)
        raise VehicleOfflineError("Автомобиль не проснулся. Проверьте, что у него есть связь.")

    # -- commands --
    def send_command(self, vin: str, command: str, payload: dict | None = None) -> None:
        if self.config.uses_proxy:
            base = self.config.proxy_url.strip()
            verify: bool | str = self.config.proxy_ca_cert.strip() or True
        else:
            base, verify = None, True
        path = f"/api/1/vehicles/{vin}/command/{command}"

        try:
            result = self._request("POST", path, base=base, json=payload or {}, verify=verify)
        except VehicleAsleepError:
            self.wake_up(vin)
            result = self._request("POST", path, base=base, json=payload or {}, verify=verify)

        if isinstance(result, dict) and result.get("result") is False:
            reason = result.get("reason") or "неизвестная причина"
            if reason in ("already_set", "already on", "already off", "is_charging"):
                return
            raise CommandFailedError(f"Автомобиль отклонил команду: {reason}")

    def lock(self, vin: str) -> None:
        self.send_command(vin, "door_lock")

    def unlock(self, vin: str) -> None:
        self.send_command(vin, "door_unlock")

    def climate_on(self, vin: str) -> None:
        self.send_command(vin, "auto_conditioning_start")

    def climate_off(self, vin: str) -> None:
        self.send_command(vin, "auto_conditioning_stop")

    def set_temperature(self, vin: str, celsius: float) -> None:
        self.send_command(vin, "set_temps", {"driver_temp": celsius, "passenger_temp": celsius})
