from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from words_generator.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Words Generator")
    app.setOrganizationName("NUTIS-YT")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
