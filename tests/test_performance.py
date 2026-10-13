import json
import sys
from types import SimpleNamespace

import httpx
import pytest

from converter.config import ProviderConfig
from converter.llm_budget import estimate_input_tokens
from converter.models import Segment
from converter.providers import OnlineProvider


def test_online_packs_requests_without_duplicate_context_or_budget_overflow():
    profile = ProviderConfig(
        endpoint="https://mock.example/v1/chat/completions", model="test", auth_header=""
    )
    calls = []

    def handler(request):
        messages = json.loads(request.content)["messages"]
        assert estimate_input_tokens(messages) <= 3584
        items = json.loads(messages[1]["content"])
        calls.append(items)
        assert all(not item["context"] for item in items)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({s["id"]: s["text"] for s in items})
        }}]})

    provider = OnlineProvider(profile, "", client=httpx.Client(transport=httpx.MockTransport(handler)))
    text = "系统启动后读取传感器的数据并检查控制器的电源连接。"
    segments = [Segment(str(i), text, context=text) for i in range(120)]
    assert provider.translate(segments, {}) == {s.id: text for s in segments}
    assert len(calls) <= 7
    assert [s["id"] for call in calls for s in call] == [s.id for s in segments]
    provider.close()


def test_online_keeps_context_that_contains_additional_information():
    provider = OnlineProvider(ProviderConfig(
        endpoint="https://mock.example/v1/chat/completions", model="test", auth_header=""
    ), "")
    messages, _ = provider._messages([Segment("a", "控制器", context="检查控制器的电源。")], {})
    assert json.loads(messages[1]["content"])[0]["context"] == "检查控制器的电源。"
    provider.close()


def test_online_keeps_original_meaning_of_glossary_placeholders_in_context():
    provider = OnlineProvider(ProviderConfig(
        endpoint="https://mock.example/v1/chat/completions", model="test", auth_header=""
    ), "")
    text = "控制器检查传感器。"
    messages, _ = provider._messages([Segment("a", text, context=text)], {"控制器": "Controller"})
    item = json.loads(messages[1]["content"])[0]
    assert "控制器" not in item["text"] and "__CVT_0__" in item["text"]
    assert item["context"] == text
    provider.close()


def test_online_packing_budget_includes_json_escapes_and_distinct_context():
    calls = []

    def handler(request):
        messages = json.loads(request.content)["messages"]
        assert estimate_input_tokens(messages) <= 1400
        items = json.loads(messages[1]["content"])
        calls.extend(items)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({s["id"]: s["text"] for s in items})
        }}]})

    provider = OnlineProvider(ProviderConfig(
        endpoint="https://mock.example/v1/chat/completions", model="test", auth_header="",
        context_window_tokens=2400, max_output_tokens=800, token_safety_margin=200,
    ), "", client=httpx.Client(transport=httpx.MockTransport(handler)))
    segments = [Segment(str(i), '检查"控制器"\\数据\n。', context='上下文"说明"\\下一行\n。')
                for i in range(40)]
    assert provider.translate(segments, {}) == {s.id: s.source for s in segments}
    assert len(calls) == len(segments)
    assert all(s["context"] == segments[0].context for s in calls)
    provider.close()


def test_offline_runtime_reuses_tokenizer_and_preserves_decoder_settings(monkeypatch, tmp_path):
    from converter.argos_runtime import ArgosRuntime

    builds, decoded, threads = [], [], []

    def pipeline(**kwargs):
        builds.append(kwargs)
        return lambda text: SimpleNamespace(sentences=[SimpleNamespace(text=text)])

    class Translator:
        def __init__(self, *args, **kwargs):
            pass

        def translate_batch(self, tokens, **kwargs):
            decoded.append(kwargs)
            return [SimpleNamespace(hypotheses=[["English", *item]], scores=[0]) for item in tokens]

    monkeypatch.setitem(sys.modules, "stanza", SimpleNamespace(Pipeline=pipeline))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(set_num_threads=threads.append))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(Translator=Translator))
    package = SimpleNamespace(
        package_path=tmp_path, from_code="zh", target_prefix="",
        tokenizer=SimpleNamespace(encode=lambda text: [text], decode=lambda tokens: " ".join(tokens)),
    )
    runtime = ArgosRuntime(package)
    assert runtime.translate("第一段。\n第二段。") == "English 第一段。\nEnglish 第二段。"
    assert runtime.translate("第三段。") == "English 第三段。"
    assert len(builds) == 1
    assert threads == [1]
    assert all(x["beam_size"] == 4 and x["num_hypotheses"] == 1 for x in decoded)
    assert all(x["length_penalty"] == .2 and x["return_scores"] for x in decoded)
    count = len(decoded)
    assert runtime.translate("第三段。") == "English 第三段。"
    assert len(decoded) == count


def test_online_partial_requests_are_checkpointed_before_pause(word_file, store):
    from converter.pipeline import Paused, Pipeline

    job = store.add(word_file)
    doc = Pipeline(store).parse(job, "eng")
    source = "系统启动后读取传感器的数据并检查控制器的电源连接。" * 2
    for segment in doc.segments:
        segment.source = source
        segment.context = source
    store.save_document(job, doc)
    calls = []

    def handler(request):
        items = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.append(items)
        if len(calls) == 2:
            checkpoint = store.load_document(job)
            assert any(s.target is not None for s in checkpoint.segments)
            assert not checkpoint.complete()
            raise Paused()
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({s["id"]: "English text" for s in items})
        }}]})

    provider = OnlineProvider(ProviderConfig(
        endpoint="https://mock.example/v1/chat/completions", model="test", auth_header="",
        context_window_tokens=2400, max_output_tokens=800, token_safety_margin=200,
    ), "", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(Paused):
        Pipeline(store).translate(job, provider, {}, "eng")
    saved = {s.id: s.target for s in store.load_document(job).segments if s.target is not None}
    assert saved
    progress = []
    Pipeline(store, progress=lambda *args: progress.append(args)).translate(job, provider, {}, "eng")
    assert store.load_document(job).complete()
    assert all(store.load_document(job).by_id()[sid].target == text for sid, text in saved.items())
    assert len({event[2] for event in progress}) > 1
    provider.close()


def test_translation_phase_is_reported_before_waiting_for_first_provider_response(
    word_file, store, provider
):
    from converter.pipeline import Pipeline

    job = store.add(word_file)
    progress = []
    translate = provider.translate

    def checked_translate(segments, glossary):
        assert progress[-1][1] == "Đang dịch"
        return translate(segments, glossary)

    provider.translate = checked_translate
    Pipeline(store, progress=lambda *args: progress.append(args)).translate(job, provider, {}, "eng")
    translating = [event for event in progress if event[1] == "Đang dịch"]
    assert translating[0][2] == 0
    assert translating[0][3] == len(store.load_document(job).segments)
    assert translating[-1][2] == translating[-1][3]


def test_old_argos_pdf_profile_blocks_resume_but_allows_historical_export(
    text_pdf, store, tmp_path
):
    import hashlib

    from converter.pipeline import Pipeline
    from converter.providers import ArgosProvider

    job = store.add(text_pdf)
    pipeline = Pipeline(store)
    doc = pipeline.parse(job, "eng")
    doc.segments[0].target = "Saved historical translation"
    doc.segments[1].source = "中" * 1000
    doc.segments[1].target = None
    store.save_document(job, doc)
    old_payload = json.dumps(
        {"kind": "argos", "profile": {"model": "translate-zh_en-1_9", "runtime": "1.9.6"},
         "glossary": {}, "prompt_version": 4},
        ensure_ascii=False, sort_keys=True,
    )
    store.update(job, profile=hashlib.sha256(old_payload.encode()).hexdigest())

    class MustNotTranslate:
        def translate(self, text):
            pytest.fail("Old profile must be rejected before inference")

    provider = ArgosProvider()
    provider.translation = MustNotTranslate()
    with pytest.raises(ValueError, match="Provider/model/glossary"):
        pipeline.translate(job, provider, {}, "eng")
    saved = store.load_document(job)
    assert saved.segments[0].target == "Saved historical translation"
    assert saved.segments[1].target is None
    for segment in saved.segments:
        if segment.target is None:
            segment.target = "Another historical translation"
    store.save_document(job, saved)
    result = pipeline.run(job, None, "markdown", tmp_path / "out", export_only=True)
    assert result["markdown"]["status"] == "done"
