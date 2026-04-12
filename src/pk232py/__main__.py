"""
pk232py – Einstiegspunkt.

Starten mit:
    python -m pk232py
oder nach Installation:
    pk232py
"""

import sys
import logging

from PyQt6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def main() -> None:
    """Hauptfunktion – initialisiert Qt und startet das Hauptfenster."""
    # Logging konfigurieren (DEBUG während der Entwicklung)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("PK232PY")
    app.setApplicationVersion("0.1.0-dev")
    app.setOrganizationName("OE3GAS")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
