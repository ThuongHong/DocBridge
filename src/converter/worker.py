from __future__ import annotations

from pathlib import Path

from .config import ProviderConfig
from .pipeline import Cancelled, Paused, Pipeline
from .providers import ArgosProvider, OnlineProvider
from .store import Store


def run_jobs(root: str, job_ids: list[str], options: dict, api_key: str, queue, pause, cancel):
    """Spawn-safe entry point. The API key is transient and never written to the job store."""
    store = Store(Path(root))
    provider = None

    def control():
        if cancel.is_set():
            raise Cancelled()
        if pause.is_set():
            raise Paused()

    try:
        if not options.get("export_only") and options.get("operation", "translate") != "convert":
            provider = (
                ArgosProvider(options.get("argos_model") or None)
                if options["provider"] == "offline"
                else OnlineProvider(ProviderConfig(**options["profile"]), api_key)
            )
        for job_id in job_ids:
            if pause.is_set() or cancel.is_set():
                break
            queue.put({"kind": "started", "id": job_id})
            operation = (
                store.get(job_id)["operation"]
                if options.get("export_only") else options.get("operation", "translate")
            )
            store.update(job_id, provider="" if operation == "convert" else options["provider"])
            pipeline = Pipeline(
                store,
                progress=lambda jid, message, done, total: queue.put(
                    {
                        "kind": "progress",
                        "id": jid,
                        "message": message,
                        "done": done,
                        "total": total,
                    }
                ),
                control=control,
            )
            try:
                pipeline.run(
                    job_id,
                    provider,
                    options["mode"],
                    Path(options["output_dir"]),
                    options.get("glossary", {}),
                    options["ocr_language"],
                    export_only=options.get("export_only", False),
                    operation=operation,
                )
            except Exception as exc:
                queue.put({"kind": "error", "id": job_id, "message": str(exc)})
            queue.put({"kind": "job_finished", "id": job_id})
    except Exception as exc:
        # Initialization failures still get persisted for each selected job.
        for job_id in job_ids:
            store.update(job_id, status="failed", error=str(exc))
        queue.put({"kind": "error", "message": str(exc)})
    finally:
        if provider:
            provider.close()
        queue.put({"kind": "finished"})


def test_online(profile: dict, api_key: str, queue):
    provider = None
    try:
        provider = OnlineProvider(ProviderConfig(**profile), api_key)
        provider.test_connection()
        queue.put({"kind": "connection", "success": True, "message": "Kết nối thành công."})
    except Exception as exc:
        queue.put({"kind": "connection", "success": False, "message": str(exc)})
    finally:
        if provider:
            provider.close()
