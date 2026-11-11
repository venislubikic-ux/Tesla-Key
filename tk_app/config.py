"""Non-secret application settings, stored as JSON in %APPDATA%\\TK\\config.json.

Secrets (client secret, OAuth tokens) are NOT stored here — see secure_store.py.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

# Official Fleet API regional base URLs
REGION_BASE_URLS = {
    "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",   # Europe, Middle East, Africa
    "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",   # North America, Asia-Pacific
    "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.cn",    # China
}
REGION_LABELS = {
    "eu": "Европа / Ближний Восток / Африка",
    "na": "Северная Америка / Азия-Тихий океан",
    "cn": "Китай",
}


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    path = Path(base) / "TK"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """Path to a bundled resource; works both from source and from a PyInstaller .exe."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


@dataclass
class AppConfig:
    client_id: str = ""
    redirect_uri: str = "http://localhost:8765/callback"
    region: str = "eu"
    # Signed-command proxy (tesla-http-proxy). Empty = send commands directly to Fleet API
    # (works only for pre-2021 Model S/X).
    proxy_url: str = "https://localhost:4443"
    proxy_ca_cert: str = ""
    # Domain registered as the partner application (used for the virtual key pairing link)
    partner_domain: str = ""
    confirm_commands: bool = True
    auto_refresh_seconds: int = 60
    selected_vin: str = ""
    selected_name: str = ""

    @property
    def fleet_base_url(self) -> str:
        return REGION_BASE_URLS.get(self.region, REGION_BASE_URLS["eu"])

    @property
    def uses_proxy(self) -> bool:
        return bool(self.proxy_url.strip())

    @classmethod
    def path(cls) -> Path:
        return data_dir() / "config.json"

    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls()
        try:
            raw = json.loads(cls.path().read_text(encoding="utf-8"))
            known = {f.name for f in fields(cls)}
            for key, value in raw.items():
                if key in known:
                    setattr(cfg, key, value)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # Corrupt config — start from defaults rather than crash
            pass
        return cfg

    def save(self) -> None:
        tmp = self.path().with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path())

    def is_configured(self) -> bool:
        return bool(self.client_id.strip() and self.redirect_uri.strip())
