from __future__ import annotations

import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    from PySide6.QtWidgets import QApplication, QTabWidget

    from .ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("DocBridge")
    app.setOrganizationName("DocBridge")
    window = MainWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        import json
        from pathlib import Path

        index = sys.argv.index("--smoke-test")
        target = Path(sys.argv[index + 1])
        app.processEvents()
        result = {
            "application": app.applicationName(),
            "main_tabs": len(window.centralWidget().findChildren(QTabWidget)),
            "tasks": window.operation_combo.count(),
            "review_dialog": bool(window.review_dialog),
            "output_modes": window.mode_combo.count(),
            "profile_loaded": bool(window.profile.name),
            "theme": window.theme,
            "language": window.language,
            "glossary_terms": len(window.glossary_entries()),
            "settings_sections": window.settings_tabs.count(),
        }
        if "--offline-smoke" in sys.argv:
            import socket

            from .models import Segment
            from .providers import ArgosProvider

            def deny_network(*args, **kwargs):
                raise RuntimeError("Network disabled during offline smoke test")

            socket.create_connection = deny_network
            socket.socket.connect = deny_network
            provider = ArgosProvider(window.argos_model_edit.text().strip() or None)
            result["offline_translation"] = provider.translate(
                [
                    Segment("plain", "你好，这是一个离线翻译测试。"),
                    Segment("technical", "运行时环境连接应用软件组件，型号 AC-123。"),
                ],
                window.glossary(),
            )
            result["offline_network_blocked"] = True
            provider.close()
        target.write_text(
            json.dumps(result, ensure_ascii=False),
            encoding="utf-8",
        )
        window.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
