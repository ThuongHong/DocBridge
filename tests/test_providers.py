import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from converter.config import ProviderConfig
from converter.glossary import default_glossary
from converter.models import Segment
from converter.providers import ArgosProvider, OnlineProvider, TranslationError, protect, restore


def config():
    return ProviderConfig(
        endpoint="https://provider.example/v1/chat/completions", model="fixed-model", retries=1
    )


def completion(content):
    return httpx.Response(
        200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    )


def test_api_fixed_model_and_placeholder_restoration():
    def handler(request):
        data = json.loads(request.content)
        assert data["model"] == "fixed-model"
        assert request.headers["Authorization"] == "Bearer test-key"
        segments = json.loads(data["messages"][1]["content"])
        assert "__CVT_0__" in segments[0]["text"]
        return completion(json.dumps({segments[0]["id"]: "Product __CVT_0__ at __CVT_1__"}))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OnlineProvider(config(), "test-key", client=client)
    result = provider.translate([Segment("a", "商品 AC-123 100%")], {})
    assert result["a"] == "Product AC-123 at 100%"


@pytest.mark.parametrize(
    "value", ['{"a":"One","a":"Two"}', '{"extra":"Wrong"}', '{"a":""}', '{"a":"Lost placeholder"}']
)
def test_invalid_responses_are_not_saved(value):
    client = httpx.Client(transport=httpx.MockTransport(lambda _: completion(value)))
    provider = OnlineProvider(config(), "test-key", client=client)
    with pytest.raises(TranslationError):
        provider.translate([Segment("a", "金额100")], {})


def test_401_does_not_retry_or_leak_key():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text="test-key private document")

    provider = OnlineProvider(
        config(), "test-key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(TranslationError) as error:
        provider.translate([Segment("a", "你好")], {})
    assert len(calls) == 1
    assert "test-key" not in str(error.value)
    assert "private document" not in str(error.value)


def test_retry_after_429_is_bounded():
    calls, waits = [], []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "999"})
            if len(calls) == 1
            else completion('{"a":"Hello"}')
        )

    provider = OnlineProvider(
        config(),
        "test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=waits.append,
    )
    assert provider.translate([Segment("a", "你好")], {}) == {"a": "Hello"}
    assert waits == [30]


def test_argos_adapter_protects_numbers_and_glossary_without_translating_tags():
    # Exercise application integration only; do not benchmark/reassess the accepted Argos model.
    class InstalledTranslation:
        def translate(self, text):
            assert "__CVT" not in text
            return {"价格": "Price", "元": "yuan", "您好": "Hello"}.get(text.strip(), text)

    provider = ArgosProvider()
    provider.translation = InstalledTranslation()
    result = provider.translate(
        [Segment("a", "价格100元"), Segment("b", "您好公司")], {"公司": "Company"}
    )
    assert result == {"a": "Price 100 yuan", "b": "Hello Company"}


@pytest.mark.parametrize("authenticated", [True, False])
def test_custom_provider_authentication_and_generation_settings(authenticated):
    profile = ProviderConfig(
        endpoint="http://localhost:1234/v1/chat/completions",
        model="chosen-model", auth_header="api-key" if authenticated else "",
        auth_prefix="", max_output_tokens=12345, context_window_tokens=32768,
    )

    def handler(request):
        assert str(request.url) == profile.endpoint
        assert "Authorization" not in request.headers
        assert request.headers.get("api-key") == ("secret" if authenticated else None)
        body = json.loads(request.content)
        assert body["model"] == "chosen-model"
        assert body["max_tokens"] == 12345
        return completion('{"a":"Hello"}')

    provider = OnlineProvider(
        profile, "secret" if authenticated else "",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert provider.translate([Segment("a", "你好")], {}) == {"a": "Hello"}
    provider.close()


def test_selected_argos_model_is_isolated_cached_and_changes_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVERTER_DATA_DIR", str(tmp_path / "data"))
    first = tmp_path / "first.argosmodel"
    second = tmp_path / "second.argosmodel"
    first.write_bytes(b"model one")
    second.write_bytes(b"model two")
    settings = SimpleNamespace()
    installed_paths = []

    def installed():
        assert settings.package_dirs == [settings.package_data_dir]
        return [SimpleNamespace(from_code="zh", to_code="en")] if (
            settings.package_data_dir / "installed"
        ).exists() else []

    def install(path):
        installed_paths.append(path)
        (settings.package_data_dir / "installed").touch()

    runtime = SimpleNamespace(
        package=SimpleNamespace(get_installed_packages=installed, install_from_path=install),
        settings=settings,
        translate=SimpleNamespace(get_translation_from_codes=lambda *_: object()),
    )
    monkeypatch.setitem(sys.modules, "argostranslate", runtime)
    one = ArgosProvider(str(first))
    one.prepare()
    first_cache = settings.package_data_dir
    ArgosProvider(str(first)).prepare()
    two = ArgosProvider(str(second))
    two.prepare()
    assert installed_paths == [first, second]
    assert first_cache != settings.package_data_dir
    assert one.fingerprint({}) != two.fingerprint({})


def test_bundled_glossary_prefers_longest_phrase_and_preserves_codes():
    glossary = default_glossary()
    source = "线控制动执行器 AC-123 100%"
    masked, values = protect(source, glossary)
    result = restore(masked, values)
    assert result == glossary["线控制动执行器"] + " AC-123 100%"


def test_argos_glossary_acronyms_keep_word_spacing():
    class InstalledTranslation:
        def translate(self, text):
            return {"连接": "connects", "和": "and", "。": "."}[text]

    provider = ArgosProvider()
    provider.translation = InstalledTranslation()
    result = provider.translate(
        [Segment("a", "运行时环境连接应用软件组件和基础软件。")],
        {"运行时环境": "Runtime Environment (RTE)",
         "应用软件组件": "Application Software Component (SWC)",
         "基础软件": "Basic Software (BSW)"},
    )
    assert result["a"] == (
        "Runtime Environment (RTE) connects Application Software Component (SWC) "
        "and Basic Software (BSW)。"
    )


def test_input_budget_splits_long_chinese_segment_before_sending():
    from converter.llm_budget import estimate_input_tokens

    profile = ProviderConfig(
        endpoint="https://example.com/v1/chat/completions", model="small-context",
        context_window_tokens=2400, max_output_tokens=800, token_safety_margin=200,
    )
    calls = []

    def handler(request):
        body = json.loads(request.content)
        assert estimate_input_tokens(body["messages"]) + 800 + 200 <= 2400
        items = json.loads(body["messages"][1]["content"])
        calls.extend(items)
        return completion(json.dumps({item["id"]: item["text"] for item in items}))

    provider = OnlineProvider(
        profile, "key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    source = "中文文档" * 300
    result = provider.translate([Segment("long", source, context=source)], {})
    assert len(calls) > 1
    assert result["long"].replace(" ", "") == source
    assert "".join(item["text"] for item in calls) == source
    provider.close()


@pytest.mark.parametrize("overflow", ["context", "length", "payload"])
def test_context_errors_and_truncated_output_are_split_without_losing_terms(overflow):
    calls = []
    glossary = {"线控制动执行器": "Brake-by-wire Actuator"}

    def handler(request):
        items = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.append(items)
        if len(calls) == 1:
            if overflow == "context":
                return httpx.Response(400, json={"error": {
                    "code": "context_length_exceeded", "message": "secret-key private document"
                }})
            if overflow == "payload":
                return httpx.Response(413)
            return httpx.Response(200, json={"choices": [{
                "finish_reason": "length", "message": {"content": '{"partial":'}
            }]})
        return completion(json.dumps({item["id"]: item["text"] for item in items}))

    provider = OnlineProvider(
        config(), "key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = provider.translate([Segment("a", "前段 线控制动执行器 AC-123 100% 后段")], glossary)
    assert len(calls) > 1
    assert "Brake-by-wire Actuator" in result["a"]
    assert "AC-123" in result["a"] and "100%" in result["a"]
    assert set(result) == {"a"}
    provider.close()


def test_unsplittable_context_error_stops_and_does_not_leak_provider_text():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"error": {
            "code": "context_length_exceeded", "message": "secret-key private document"
        }})

    provider = OnlineProvider(
        config(), "key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(TranslationError) as error:
        provider.translate([Segment("a", "中")], {})
    assert len(calls) == 1
    assert "secret-key" not in str(error.value) and "private document" not in str(error.value)
    provider.close()


def test_server_failure_retries_without_context_splitting():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    provider = OnlineProvider(
        config(), "key", sleep=lambda _: None,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(TranslationError):
        provider.translate([Segment("a", "前半后半"), Segment("b", "内容")], {})
    assert len(calls) == 2
    provider.close()


def test_pause_is_checked_between_automatically_split_requests():
    from converter.pipeline import Paused

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(413)

    provider = OnlineProvider(
        config(), "key", client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    def control():
        if calls:
            raise Paused()

    provider.set_control(control)
    with pytest.raises(Paused):
        provider.translate([Segment("a", "前半后半")], {})
    assert len(calls) == 1
    provider.close()
