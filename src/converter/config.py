from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .models import atomic_text


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def environment(name: str) -> str | None:
    """Prefer DocBridge settings, retaining existing Converter overrides."""
    return os.environ.get("DOCBRIDGE_" + name) or os.environ.get("CONVERTER_" + name)


def data_root() -> Path:
    custom = environment("DATA_DIR")
    if custom:
        return Path(custom)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        current, legacy = base / "DocBridge", base / "Converter"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        current, legacy = base / "docbridge", base / "converter"
    return legacy if legacy.exists() and not current.exists() else current


@dataclass
class ProviderConfig:
    name: str = "Dịch online"
    endpoint: str = ""
    model: str = ""
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "
    batch_chars: int = 30000
    max_output_tokens: int = 16384
    timeout_seconds: int = 120
    retries: int = 3
    context_window_tokens: int = 131072
    token_safety_margin: int = 1024
    max_concurrent_requests: int = 3

    @classmethod
    def load(cls, path: Path | None = None) -> ProviderConfig:
        override = environment("PROVIDER_CONFIG")
        default = resource_root() / "config/provider.json"
        local = resource_root() / "config/provider.local.json"
        saved = data_root() / "provider.json"
        selected = path or (
            saved if saved.exists()
            else Path(override) if override
            else local if local.exists() else default
        )
        data = json.loads(selected.read_text(encoding="utf-8")) if selected.exists() else {}
        return cls(**data)

    def save(self) -> None:
        # API keys are deliberately absent from this dataclass and file.
        atomic_text(data_root() / "provider.json", json.dumps(asdict(self), indent=2))

    def validate(self) -> None:
        parsed = urlsplit(self.endpoint)
        if not self.endpoint or not self.model:
            raise ValueError(
                "Nhập API URL và model trong Cài đặt."
            )
        if not parsed.hostname or parsed.fragment:
            raise ValueError("API URL không hợp lệ.")
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("Endpoint phải dùng HTTPS (HTTP chỉ dành cho dịch vụ trên máy).")
        if not parsed.path.rstrip("/").endswith("/chat/completions"):
            raise ValueError("Endpoint phải là URL đầy đủ tới /v1/chat/completions.")
        if not 1 <= self.max_concurrent_requests <= 8:
            raise ValueError("Số request đồng thời phải từ 1 đến 8.")
        if self.batch_chars < 100 or self.retries < 0:
            raise ValueError("Cấu hình batch/retry không hợp lệ.")
        if self.max_output_tokens < 1 or self.timeout_seconds < 1:
            raise ValueError("Giới hạn token và timeout phải lớn hơn 0.")
        if self.token_safety_margin < 0 or (
            self.context_window_tokens - self.max_output_tokens - self.token_safety_margin < 1024
        ):
            raise ValueError("Context window phải đủ chứa token đầu ra, dự phòng và ít nhất 1024 token đầu vào.")
        if any(c in self.auth_header for c in "\r\n: "):
            raise ValueError("Tên header xác thực không hợp lệ.")
        if any(c in self.auth_prefix for c in "\r\n"):
            raise ValueError("Prefix xác thực không hợp lệ.")


def normalize_endpoint(value: str) -> str:
    """Accept a service root, versioned base URL or full Chat Completions endpoint."""
    value = value.strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path += "/chat/completions" if path else "/v1/chat/completions"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def load_preferences() -> dict:
    path = data_root() / "preferences.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_preferences(data: dict) -> None:
    atomic_text(data_root() / "preferences.json", json.dumps(data, ensure_ascii=False, indent=2))


def get_api_key() -> str:
    import keyring

    try:
        return (
            keyring.get_password("DocBridge", "translation-api")
            or keyring.get_password("Converter", "translation-api") or ""
        )
    except keyring.errors.KeyringError:
        return ""


def set_api_key(value: str) -> None:
    import keyring

    if value:
        keyring.set_password("DocBridge", "translation-api", value)
    else:
        for service in ("DocBridge", "Converter"):
            try:
                keyring.delete_password(service, "translation-api")
            except keyring.errors.PasswordDeleteError:
                pass
