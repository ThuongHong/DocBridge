import pytest

from converter.config import ProviderConfig, normalize_endpoint
from converter.i18n import translate


@pytest.mark.parametrize("value,expected", [
    ("", ""),
    (" https://example.com/ ", "https://example.com/v1/chat/completions"),
    ("http://localhost:11434/v1/", "http://localhost:11434/v1/chat/completions"),
    (
        "https://example.com/openai/deployments/model/chat/completions?api-version=2024-10-21",
        "https://example.com/openai/deployments/model/chat/completions?api-version=2024-10-21",
    ),
])
def test_base_and_full_api_urls(value, expected):
    assert normalize_endpoint(value) == expected


def test_saved_provider_precedes_initial_defaults_but_explicit_path_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "data"))
    initial = tmp_path / "initial.json"
    initial.write_text('{"name":"Initial","model":"default"}')
    monkeypatch.setenv("CONVERTER_PROVIDER_CONFIG", str(initial))
    assert ProviderConfig.load().name == "Initial"
    profile = ProviderConfig(endpoint="https://example.com/v1/chat/completions", model="new")
    profile.save()
    assert ProviderConfig.load().model == "new"
    assert ProviderConfig.load(initial).model == "default"


def test_progress_and_warnings_are_localized_without_changing_document_text():
    assert translate("Đọc PDF: trang 2/8", "en") == "Reading PDF: page 2/8"
    assert translate("OCR confidence 50%: kiểm tra text nguồn.", "en") == (
        "OCR confidence 50%: check source text."
    )
    assert translate("User document: 汽车", "en") == "User document: 汽车"
    assert translate("Đang dịch", "vi") == "Đang dịch"


def test_context_window_reserves_output_and_prompt_space():
    profile = ProviderConfig(
        endpoint="https://example.com/v1/chat/completions", model="small-model",
        context_window_tokens=4096, max_output_tokens=4096,
    )
    with pytest.raises(ValueError, match="Context window"):
        profile.validate()
