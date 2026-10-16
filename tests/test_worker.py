import json
import multiprocessing as mp
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from converter.config import ProviderConfig
from converter.worker import run_jobs


def test_spawned_worker_uses_chat_completions_and_persists_both_outputs(word_file, store, tmp_path):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(data)
            items = json.loads(data["messages"][1]["content"])
            translated = {item["id"]: "English " + item["text"] for item in items}
            payload = json.dumps(
                {
                    "choices": [
                        {"message": {"content": json.dumps(translated)}, "finish_reason": "stop"}
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = mp.get_context("spawn")
    events = context.Queue()
    job = store.add(word_file)
    options = {
        "provider": "online",
        "mode": "both",
        "output_dir": str(tmp_path / "output"),
        "ocr_language": "eng",
        "profile": asdict(
            ProviderConfig(
                endpoint=f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                model="configured-model",
            )
        ),
    }
    pause, cancel = context.Event(), context.Event()
    process = context.Process(
        target=run_jobs,
        args=(
            str(store.root),
            [job],
            options,
            "transient-key",
            events,
            pause,
            cancel,
        ),
    )
    try:
        process.start()
        process.join(timeout=20)
        assert not process.is_alive()
        assert process.exitcode == 0
        result = store.get(job)
        assert result["status"] == "done_warnings", result["error"]
        assert {value["status"] for value in result["exports"].values()} == {"done"}
        assert calls and all(call["model"] == "configured-model" for call in calls)
        assert store.load_document(job).complete()
        assert "transient-key" not in store.document_path(job).read_text()
        assert "transient-key" not in Path(store.path).read_bytes().decode(errors="ignore")
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        events.close()
        server.shutdown()
        server.server_close()


def test_worker_propagates_readable_excel_layout_on_historical_export(store, tmp_path):
    from queue import Queue
    from threading import Event

    import openpyxl

    from converter.pipeline import Pipeline

    source = tmp_path / 'layout.xlsx'
    book = openpyxl.Workbook()
    book.active['A1'] = '检查'
    book.active.column_dimensions['A'].width = 10
    book.active.row_dimensions[1].height = 16
    book.save(source)
    job = store.add(source)
    doc = Pipeline(store).parse(job, 'eng')
    for segment in doc.segments:
        segment.target = 'The construction safety measures must be inspected before work begins.'
    store.save_document(job, doc)
    options = {'provider': 'offline', 'mode': 'office', 'output_dir': str(tmp_path / 'output'),
               'ocr_language': 'eng', 'export_only': True, 'excel_layout': 'readable'}
    run_jobs(str(store.root), [job], options, '', Queue(), Event(), Event())
    result = store.get(job)
    assert result['exports']['office']['status'] == 'done', result['error']
    sheet = openpyxl.load_workbook(result['exports']['office']['path']).active
    assert sheet.row_dimensions[1].height > 16
    assert store.load_document(job).coverage['layout']['mode'] == 'readable'
