import json

import httpx
import pytest

from converter.config import ProviderConfig
from converter.models import Segment
from converter.providers import ArgosProvider, OnlineProvider, TranslationError


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
