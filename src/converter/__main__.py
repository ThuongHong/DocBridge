from __future__ import annotations

import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    from PySide6.QtWidgets import QApplication

    from .ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Converter")
    app.setOrganizationName("Converter")
    window = MainWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        import json
        from pathlib import Path

        index = sys.argv.index("--smoke-test")
        target = Path(sys.argv[index + 1])
        app.processEvents()
        target.write_text(
            json.dumps(
                {
                    "tabs": window.tabs.count(),
                    "output_modes": window.mode_combo.count(),
                    "profile_loaded": bool(window.profile.name),
                }
            ),
            encoding="utf-8",
        )
        window.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
