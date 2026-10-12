from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .models import atomic_text


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def data_root() -> Path:
    custom = os.environ.get("CONVERTER_DATA_DIR")
    if custom:
        return Path(custom)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Converter"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "converter"


@dataclass
class ProviderConfig:
    name: str = "Dịch online"
    endpoint: str = ""
    model: str = ""
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    batch_chars: int = 6000
    max_output_tokens: int = 4096
    timeout_seconds: int = 120
    retries: int = 3

    @classmethod
    def load(cls, path: Path | None = None) -> ProviderConfig:
        override = os.environ.get("CONVERTER_PROVIDER_CONFIG")
        default = resource_root() / "config/provider.json"
        local = resource_root() / "config/provider.local.json"
        selected = path or (Path(override) if override else local if local.exists() else default)
        data = json.loads(selected.read_text(encoding="utf-8")) if selected.exists() else {}
        return cls(**data)

    def validate(self) -> None:
        from urllib.parse import urlsplit

        parsed = urlsplit(self.endpoint)
        if not self.endpoint or not self.model:
            raise ValueError(
                "Chưa cấu hình dịch vụ online. Nhà phát triển cần điền endpoint và model."
            )
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("Endpoint phải dùng HTTPS (HTTP chỉ dành cho dịch vụ trên máy).")
        if not parsed.path.rstrip("/").endswith("/chat/completions"):
            raise ValueError("Endpoint phải là URL đầy đủ tới /v1/chat/completions.")
        if self.batch_chars < 100 or self.retries < 0:
            raise ValueError("Cấu hình batch/retry không hợp lệ.")


def load_preferences() -> dict:
    path = data_root() / "preferences.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_preferences(data: dict) -> None:
    atomic_text(data_root() / "preferences.json", json.dumps(data, ensure_ascii=False, indent=2))


def get_api_key() -> str:
    import keyring

    try:
        return keyring.get_password("Converter", "translation-api") or ""
    except keyring.errors.KeyringError:
        return ""


def set_api_key(value: str) -> None:
    import keyring

    if value:
        keyring.set_password("Converter", "translation-api", value)
    else:
        try:
            keyring.delete_password("Converter", "translation-api")
        except keyring.errors.PasswordDeleteError:
            pass
