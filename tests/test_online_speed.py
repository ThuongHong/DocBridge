import json
import threading

import httpx
import pytest

from converter.config import ProviderConfig
from converter.llm_budget import estimate_input_tokens
from converter.models import Segment
from converter.providers import OnlineProvider


def test_cjk_estimate_does_not_charge_utf8_bytes_as_tokens():
    assert estimate_input_tokens([{'role': 'user', 'content': '汽车控制系统' * 1000}]) < 12000


def test_public_large_context_defaults_remain_provider_neutral():
    p = ProviderConfig()
    assert p.model == p.endpoint == ''
    assert p.batch_chars == 30000
    assert p.max_output_tokens == 16384
    assert p.context_window_tokens == 131072


def test_parallel_requests_checkpoint_on_caller_thread_and_resume(word_file, store):
    from converter.pipeline import Paused, Pipeline

    job = store.add(word_file)
    doc = Pipeline(store).parse(job, 'eng')
    doc.segments = [Segment(str(i), '汽车系统' * 30) for i in range(6)]
    store.save_document(job, doc)
    barrier = threading.Barrier(3)
    calls = []
    lock = threading.Lock()
    parallel = True

    def handler(request):
        items = json.loads(json.loads(request.content)['messages'][1]['content'])
        with lock:
            calls.extend(s['id'] for s in items)
        if parallel:
            barrier.wait(timeout=2)
        return httpx.Response(200, json={'choices': [{'message': {
            'content': json.dumps({s['id']: 'English' for s in items})}}]})

    p = OnlineProvider(ProviderConfig(endpoint='https://mock.example/v1/chat/completions',
        model='test', auth_header='', batch_chars=100, max_concurrent_requests=3), '',
        client=httpx.Client(transport=httpx.MockTransport(handler)))
    main = threading.get_ident()
    original_save = store.save_document
    saves = []

    def save(jid, document):
        assert threading.get_ident() == main
        original_save(jid, document)
        saves.append(sum(s.target is not None for s in document.segments))

    store.save_document = save

    def progress(jid, msg, done, total):
        if done:
            raise Paused()

    with pytest.raises(Paused):
        Pipeline(store, progress=progress).translate(job, p, {}, 'eng')
    saved = {s.id for s in store.load_document(job).segments if s.target is not None}
    assert saved and saves
    parallel = False
    calls.clear()
    Pipeline(store).translate(job, p, {}, 'eng')
    assert store.load_document(job).complete()
    assert saved.isdisjoint(calls)
    p.close()


def test_atomic_checkpoint_retries_transient_file_lock(tmp_path, monkeypatch):
    import os

    from converter.models import atomic_text

    path = tmp_path / 'checkpoint.json'
    path.write_text('old')
    replace = os.replace
    attempts = []

    def locked(source, destination):
        attempts.append(1)
        if len(attempts) < 3:
            assert path.read_text() == 'old'
            raise PermissionError('Transient lock')
        replace(source, destination)

    monkeypatch.setattr(os, 'replace', locked)
    monkeypatch.setattr('time.sleep', lambda seconds: None)
    atomic_text(path, 'new')
    assert path.read_text() == 'new'
    assert len(attempts) == 3
    assert list(tmp_path.iterdir()) == [path]


def test_output_budget_limits_batches_before_truncation():
    profile = ProviderConfig(endpoint='https://mock.example/v1/chat/completions',
                             model='test', auth_header='', max_output_tokens=800,
                             max_concurrent_requests=1)
    provider = OnlineProvider(profile, '')
    parts = list(provider._pack_batches([Segment(str(i), '中' * 200) for i in range(20)], {}))
    assert len(parts) >= 10
    provider.close()


def test_legacy_online_profile_can_resume_after_concurrency_field_added():
    from dataclasses import asdict

    from converter.providers import signature

    config = ProviderConfig(endpoint='https://mock.example/v1/chat/completions',
                            model='test', auth_header='', batch_chars=6000,
                            max_output_tokens=4096, context_window_tokens=8192,
                            token_safety_margin=512)
    legacy = asdict(config)
    legacy.pop('max_concurrent_requests')
    provider = OnlineProvider(config, '')
    assert provider.fingerprint({}) == signature('online', legacy, {})
    config.max_concurrent_requests = 1
    assert provider.fingerprint({}) == signature('online', legacy, {})
    legacy['model'] = 'other-service-model'
    assert provider.fingerprint({}) != signature('online', legacy, {})
    provider.close()
