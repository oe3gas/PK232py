"""
opmode_rtty_base.py – Gemeinsame Basisklasse für RTTY-artige Opmode-Screens.

Verwendet von:
  baudot_screen.py  → BaudotScreen(RttyBaseScreen)
  ascii_screen.py   → AsciiScreen(RttyBaseScreen)

Was die Basisklasse enthält (alles Gemeinsame):
  - Stil-Konstanten
  - MacroStore  (Laden/Speichern Macro.txt)
  - MacroEditDialog
  - RttyBaseScreen
      • Titel-Label         (wird von Unterklasse gesetzt)
      • RBAUD-Dropdown
      • Reihe 1: SEND / RECEIVE (prominent, blinkend)
      • Reihe 2: mode_buttons() — abstrakt, von Unterklasse implementiert
      • RX-Fenster
      • TX-Fenster (5 Zeilen)
      • Macro-Sektion

Was die Unterklasse liefert:
  - MODE_TITLE : str          z.B. "Baudot" oder "ASCII RTTY"
  - _build_mode_buttons(layout) : baut Reihe 2 in den übergebenen QHBoxLayout
"""

import os
from datetime import datetime, timezone
from PyQt6.QtWidgets import (
    QWidget, QDialog, QScrollArea, QFrame,
    QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton,
    QComboBox, QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, QEvent
from PyQt6.QtGui import QFont, QKeyEvent


# ---------------------------------------------------------------------------
# Layout-Konstanten  (für alle RTTY-Screens gleich)
# ---------------------------------------------------------------------------

BTN_W      = 90
SPACING    = 6
ROW2_TOTAL = 7 * BTN_W + 6 * SPACING   # 7 Buttons in Reihe 2
PROM_W     = (ROW2_TOTAL - SPACING) // 2

MACRO_COUNT    = 6
MACRO_NAME_MAX = 10
MACRO_TEXT_MAX = 200
MACRO_FILE     = "Macro.txt"

# RBAUD-Werte gelten für Baudot UND ASCII
RBAUD_VALUES = ["45", "50", "57", "75", "100", "110", "150", "200", "300"]


# ---------------------------------------------------------------------------
# Stile
# ---------------------------------------------------------------------------

STYLE_PROM_INACTIVE = (
    "QPushButton {"
    "  background-color: #555555; color: #cccccc;"
    "  border: 2px solid #444444; border-radius: 6px;"
    "  font-size: 13pt; font-weight: bold; padding: 6px;"
    "}"
)
STYLE_SEND_ON = (
    "QPushButton {"
    "  background-color: #cc2222; color: white;"
    "  border: 2px solid #991111; border-radius: 6px;"
    "  font-size: 13pt; font-weight: bold; padding: 6px;"
    "}"
)
STYLE_SEND_BLINK = (
    "QPushButton {"
    "  background-color: #ff7777; color: white;"
    "  border: 2px solid #cc2222; border-radius: 6px;"
    "  font-size: 13pt; font-weight: bold; padding: 6px;"
    "}"
)
STYLE_RECEIVE_ON = (
    "QPushButton {"
    "  background-color: #3a9e3a; color: white;"
    "  border: 2px solid #2a7a2a; border-radius: 6px;"
    "  font-size: 13pt; font-weight: bold; padding: 6px;"
    "}"
)


# ---------------------------------------------------------------------------
# Hilfs-Funktionen  (werden von Screen und Dialog benutzt)
# ---------------------------------------------------------------------------

def make_toggle_button(label: str) -> QPushButton:
    """Kleiner Toggle-Button: grün = ON, grau = OFF.

    NoFocus: Ein Mausklick auf diesen Button gibt ihm NIEMALS den
    Keyboard-Focus – der Cursor im TX-Fenster bleibt aktiv.
    """
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setChecked(False)
    btn.setFixedWidth(BTN_W)
    btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # ← kein Focus-Raub
    _apply_toggle_style(btn)
    btn.toggled.connect(lambda _c, b=btn: _apply_toggle_style(b))
    return btn


def _apply_toggle_style(btn: QPushButton) -> None:
    if btn.isChecked():
        btn.setStyleSheet(
            "QPushButton { background-color: #3a9e3a; color: white;"
            " border: 1px solid #2a7a2a; border-radius: 4px; padding: 4px; }"
        )
    else:
        btn.setStyleSheet(
            "QPushButton { background-color: #888888; color: white;"
            " border: 1px solid #555555; border-radius: 4px; padding: 4px; }"
        )


def add_hline(layout) -> None:
    """Fügt eine horizontale Trennlinie in ein QVBoxLayout ein."""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    layout.addWidget(line)


# ---------------------------------------------------------------------------
# Theme-System
# ---------------------------------------------------------------------------

# Zwei vordefinierte Themes.
# Jedes Theme ist ein Dict mit allen relevanten Farb- und Stil-Schlüsseln.
# TX_COLOR / RX_COLOR: Textfarbe im TX- bzw. RX-Fenster.
# Screens die TX/RX-Fenster bauen, lesen diese Werte über get_theme().

THEMES: dict[str, dict] = {
    "dark": {
        "name":              "Dark",
        # Fenster / Widgets
        "bg_window":         "#1e2830",
        "bg_widget":         "#1e2830",
        "bg_input":          "#1a2430",
        "bg_input_tx":       "#1a2c1a",   # TX-Fenster: leicht grünlich
        "bg_button":         "#445566",
        "bg_button_hover":   "#556677",
        "bg_button_pressed": "#334455",
        "bg_button_dis":     "#333333",
        "bg_spin":           "#2a3a4a",
        "bg_combo":          "#2a3a4a",
        "bg_line":           "#1e2830",
        "bg_tooltip":        "#2a3a4a",
        # Text
        "fg_label":          "#d0e4f4",
        "fg_button":         "#ffffff",
        "fg_button_dis":     "#666666",
        "fg_groupbox":       "#ccddee",
        "fg_checkbox":       "#d0e4f4",
        "fg_spin":           "#ffffff",
        "fg_combo":          "#ffffff",
        "fg_line":           "#ffffff",
        "fg_tooltip":        "#d0e4f4",
        # RX / TX Textfarben (das Herzstück der Unterscheidung)
        "rx_color":          "#88ccff",   # hellblau  — empfangener Text
        "tx_color":          "#ffee88",   # hellgelb  — gesendeter Text
        # Rahmen
        "border_input":      "#334455",
        "border_button":     "#334455",
        "border_spin":       "#445566",
        "border_tooltip":    "#556677",
    },
    "light": {
        "name":              "Light",
        # Fenster / Widgets
        "bg_window":         "#f0f0f0",
        "bg_widget":         "#f0f0f0",
        "bg_input":          "#ffffff",
        "bg_input_tx":       "#f0fff0",   # TX-Fenster: leicht grünlich
        "bg_button":         "#d0d8e0",
        "bg_button_hover":   "#c0c8d8",
        "bg_button_pressed": "#a0b0c0",
        "bg_button_dis":     "#e0e0e0",
        "bg_spin":           "#ffffff",
        "bg_combo":          "#ffffff",
        "bg_line":           "#ffffff",
        "bg_tooltip":        "#ffffcc",
        # Text
        "fg_label":          "#1a1a2e",
        "fg_button":         "#1a1a2e",
        "fg_button_dis":     "#909090",
        "fg_groupbox":       "#1a1a2e",
        "fg_checkbox":       "#1a1a2e",
        "fg_spin":           "#000000",
        "fg_combo":          "#000000",
        "fg_line":           "#000000",
        "fg_tooltip":        "#333333",
        # RX / TX Textfarben
        "rx_color":          "#000080",   # dunkelblau — empfangener Text
        "tx_color":          "#006600",   # dunkelgrün — gesendeter Text
        # Rahmen
        "border_input":      "#a0a8b0",
        "border_button":     "#a0a8b0",
        "border_spin":       "#a0a8b0",
        "border_tooltip":    "#c8c800",
    },
}

# Aktives Theme — kann zur Laufzeit gewechselt werden
_current_theme: str = "dark"


def get_theme() -> dict:
    """Gibt das aktuell aktive Theme-Dict zurück."""
    return THEMES[_current_theme]


def set_theme(name: str) -> None:
    """Setzt das aktive Theme ('dark' oder 'light')."""
    global _current_theme
    if name in THEMES:
        _current_theme = name


def apply_app_style(app, theme: str = "dark") -> None:
    """Wendet das gewählte Theme als globales QApplication-Stylesheet an.

    Aufruf in jeder main()-Funktion:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        apply_app_style(app, "dark")   # oder "light"

    Args:
        app:   Die QApplication-Instanz.
        theme: Theme-Name: "dark" (Standard) oder "light".
    """
    set_theme(theme)
    t = get_theme()

    app.setStyleSheet(
        f"QWidget {{ background-color: {t['bg_window']}; }}"

        f"QPushButton {{"
        f"  background-color: {t['bg_button']};"
        f"  color: {t['fg_button']};"
        f"  border: 1px solid {t['border_button']};"
        f"  border-radius: 4px;"
        f"  padding: 4px 8px;"
        f"}}"
        f"QPushButton:hover {{ background-color: {t['bg_button_hover']}; }}"
        f"QPushButton:pressed {{ background-color: {t['bg_button_pressed']}; }}"
        f"QPushButton:disabled {{"
        f"  background-color: {t['bg_button_dis']};"
        f"  color: {t['fg_button_dis']};"
        f"  border: 1px solid {t['border_button']};"
        f"}}"

        f"QLabel {{ color: {t['fg_label']}; }}"
        f"QCheckBox {{ color: {t['fg_checkbox']}; }}"
        f"QGroupBox {{ color: {t['fg_groupbox']}; }}"

        f"QSpinBox {{"
        f"  background-color: {t['bg_spin']};"
        f"  color: {t['fg_spin']};"
        f"  border: 1px solid {t['border_spin']};"
        f"  border-radius: 3px;"
        f"}}"

        f"QComboBox {{"
        f"  background-color: {t['bg_combo']};"
        f"  color: {t['fg_combo']};"
        f"  border: 1px solid {t['border_spin']};"
        f"  border-radius: 3px;"
        f"  padding: 2px;"
        f"}}"
        f"QComboBox QAbstractItemView {{"
        f"  background-color: {t['bg_combo']};"
        f"  color: {t['fg_combo']};"
        f"}}"

        f"QLineEdit {{"
        f"  background-color: {t['bg_line']};"
        f"  color: {t['fg_line']};"
        f"  border: 1px solid {t['border_input']};"
        f"  border-radius: 3px;"
        f"  padding: 2px;"
        f"}}"

        # QTextEdit bekommt KEIN generisches Stylesheet —
        # RX und TX werden individuell per Klasse gesteuert (siehe unten)
        f"QTextEdit {{"
        f"  border: 1px solid {t['border_input']};"
        f"}}"

        f"QToolTip {{"
        f"  background-color: {t['bg_tooltip']};"
        f"  color: {t['fg_tooltip']};"
        f"  border: 1px solid {t['border_tooltip']};"
        f"}}"
    )


def style_rx_widget(widget) -> None:
    """Wendet RX-Farben auf ein QTextEdit an (nach apply_app_style aufrufen).

    Args:
        widget: Ein QTextEdit das als RX-Fenster dient.
    """
    t = get_theme()
    widget.setStyleSheet(
        f"QTextEdit {{"
        f"  background-color: {t['bg_input']};"
        f"  color: {t['rx_color']};"
        f"  border: 1px solid {t['border_input']};"
        f"}}"
    )


def style_tx_widget(widget) -> None:
    """Wendet TX-Farben auf ein QTextEdit an und setzt einen Block-Cursor.

    Der Block-Cursor (breiter, blinkender Balken) ist im Amateurfunk-Betrieb
    deutlich besser sichtbar als der Standard-Liniencursor — besonders beim
    schnellen Wechsel zwischen Buttons und Tastatureingabe.

    Args:
        widget: Ein QTextEdit das als TX-Fenster dient.
    """
    t = get_theme()
    widget.setStyleSheet(
        f"QTextEdit {{"
        f"  background-color: {t['bg_input_tx']};"
        f"  color: {t['tx_color']};"
        f"  border: 1px solid {t['border_input']};"
        f"}}"
    )
    # Block-Cursor: Breite = durchschnittliche Zeichenbreite der Schrift.
    # Das ergibt einen gut sichtbaren, blinkenden Block statt einer dünnen Linie.
    char_w = widget.fontMetrics().averageCharWidth()
    widget.setCursorWidth(char_w)


# ---------------------------------------------------------------------------
# MacroStore
# ---------------------------------------------------------------------------

class MacroStore:
    """Verwaltet 6 Macros (Name + Text) und deren Persistenz in Macro.txt.

    Dateiformat (plain text, user-editierbar):
        # Kommentarzeilen beginnen mit #
        NAME|TEXT
        ...

    Escape-Regeln (damit eine Datenzeile immer genau eine Zeile in der Datei ist):
        Zeichen im Text  →  gespeichert als
        \\n  (LF)         →  \\n   (Backslash + n)
        \\r  (CR)         →  \\r   (Backslash + r)
        \\   (Backslash)  →  \\\\  (doppelter Backslash)
        |                →  /    (Trennzeichen-Konflikt vermeiden)

    Beim Laden werden diese Ersetzungen in umgekehrter Reihenfolge rückgängig gemacht.
    Ein Benutzer der die Datei manuell bearbeitet kann Zeilenumbrüche im Text
    ebenfalls als \\n schreiben — sie werden beim nächsten Laden korrekt interpretiert.
    """

    def __init__(self, path: str = MACRO_FILE):
        self.path  = path
        self.names = [f"Macro {i}" for i in range(1, MACRO_COUNT + 1)]
        self.texts = [""] * MACRO_COUNT

    def load(self) -> str:
        """Gibt '' zurück bei Erfolg, sonst eine Fehlermeldung."""
        if not os.path.isfile(self.path):
            return f"Datei '{self.path}' nicht gefunden – Standardwerte werden verwendet."
        try:
            with open(self.path, encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError as exc:
            return f"Lesefehler: {exc}"

        data = [
            ln.rstrip("\n") for ln in lines
            if ln.strip() and not ln.startswith("#")
        ]
        for idx in range(MACRO_COUNT):
            if idx >= len(data):
                break
            parts = data[idx].split("|", maxsplit=1)
            self.names[idx] = self._unescape(parts[0])[:MACRO_NAME_MAX]
            self.texts[idx] = self._unescape(
                parts[1] if len(parts) > 1 else ""
            )[:MACRO_TEXT_MAX]
        return ""

    def save(self) -> str:
        """Gibt '' zurück bei Erfolg, sonst eine Fehlermeldung."""
        header = (
            "# PK232PY Macros\n"
            f"# Format: NAME|TEXT  "
            f"(Name max. {MACRO_NAME_MAX}, Text max. {MACRO_TEXT_MAX} Zeichen)\n"
            "# Zeilenumbrüche im Text werden als \\n gespeichert.\n"
            "# Diese Datei kann direkt mit einem Texteditor bearbeitet werden.\n#\n"
        )
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write(header)
                for name, text in zip(self.names, self.texts):
                    fh.write(f"{self._escape(name)}|{self._escape(text)}\n")
        except OSError as exc:
            return f"Schreibfehler: {exc}"
        return ""

    # ------------------------------------------------------------------
    # Escape / Unescape  (statische Hilfsmethoden)
    # ------------------------------------------------------------------

    @staticmethod
    def _escape(value: str) -> str:
        """Kodiert einen String für eine einzelne Dateizeile.

        Reihenfolge ist wichtig: Backslash zuerst escapen,
        sonst werden die neu eingefügten Backslashes selbst nochmal ersetzt.
        """
        value = value.replace("\\", "\\\\")   # \  →  \\
        value = value.replace("\r", "\\r")    # CR →  \r
        value = value.replace("\n", "\\n")    # LF →  \n
        value = value.replace("|",  "/")      # |  →  /
        return value

    @staticmethod
    def _unescape(value: str) -> str:
        """Dekodiert einen aus der Datei gelesenen String.

        Reihenfolge ist die Umkehrung von _escape:
        Erst CR/LF wiederherstellen, dann doppelten Backslash auflösen.
        """
        # Temporären Platzhalter verwenden damit \\\n nicht falsch interpretiert wird
        value = value.replace("\\\\", "\x00")  # \\  →  Platzhalter
        value = value.replace("\\r",  "\r")    # \r  →  CR
        value = value.replace("\\n",  "\n")    # \n  →  LF
        value = value.replace("\x00", "\\")    # Platzhalter  →  \
        return value


# ---------------------------------------------------------------------------
# MacroEditDialog
# ---------------------------------------------------------------------------

class MacroEditDialog(QDialog):
    """Modaler Dialog: 6 Macros bearbeiten, speichern, laden."""

    def __init__(self, store: MacroStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Macros bearbeiten")
        self.setMinimumWidth(620)
        self.setModal(True)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        hdr = QLabel("Macro-Editor")
        hdr.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        root.addWidget(hdr)
        add_hline(root)

        # Spalten-Header
        hrow = QHBoxLayout()
        for text, width in (("Name", 110), (f"Text  (max. {MACRO_TEXT_MAX} Zeichen)", None)):
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            if width:
                lbl.setFixedWidth(width)
            hrow.addWidget(lbl)
        root.addLayout(hrow)

        # Scroll-Bereich mit den 6 Zeilen
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(6)
        inner_layout.setContentsMargins(0, 0, 0, 0)

        self._name_edits: list[QLineEdit] = []
        self._text_edits: list[QTextEdit] = []
        mono = QFont("Courier New", 10)

        for i in range(MACRO_COUNT):
            row = QHBoxLayout()
            row.setSpacing(8)

            ne = QLineEdit()
            ne.setFont(mono)
            ne.setMaxLength(MACRO_NAME_MAX)
            ne.setFixedWidth(110)
            ne.setPlaceholderText(f"Macro {i+1}")
            row.addWidget(ne)
            self._name_edits.append(ne)

            te = QTextEdit()
            te.setFont(mono)
            te.setAcceptRichText(False)
            fm = te.fontMetrics()
            mc = te.contentsMargins()
            te.setFixedHeight(fm.lineSpacing() * 3 + mc.top() + mc.bottom() + 8)
            te.textChanged.connect(lambda edit=te: self._limit_text(edit))
            row.addWidget(te)
            self._text_edits.append(te)

            inner_layout.addLayout(row)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll)
        add_hline(root)

        # Buttons: Save / Load / Close
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        for label, slot in (("Save", self._on_save), ("Load", self._on_load)):
            b = QPushButton(label)
            b.setFixedWidth(100)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    def _populate(self) -> None:
        for i in range(MACRO_COUNT):
            self._name_edits[i].setText(self.store.names[i])
            self._text_edits[i].blockSignals(True)
            self._text_edits[i].setPlainText(self.store.texts[i])
            self._text_edits[i].blockSignals(False)

    def _collect(self) -> None:
        for i in range(MACRO_COUNT):
            self.store.names[i] = self._name_edits[i].text()
            self.store.texts[i] = self._text_edits[i].toPlainText()[:MACRO_TEXT_MAX]

    @staticmethod
    def _limit_text(te: QTextEdit) -> None:
        text = te.toPlainText()
        if len(text) > MACRO_TEXT_MAX:
            cur = te.textCursor()
            pos = cur.position()
            te.blockSignals(True)
            te.setPlainText(text[:MACRO_TEXT_MAX])
            cur.setPosition(min(pos, MACRO_TEXT_MAX))
            te.setTextCursor(cur)
            te.blockSignals(False)

    def _on_save(self) -> None:
        self._collect()
        err = self.store.save()
        if err:
            QMessageBox.warning(self, "Speichern fehlgeschlagen", err)
        else:
            QMessageBox.information(self, "Gespeichert",
                                    f"Macros in '{self.store.path}' gespeichert.")

    def _on_load(self) -> None:
        err = self.store.load()
        if err:
            QMessageBox.warning(self, "Laden fehlgeschlagen", err)
        else:
            self._populate()
            QMessageBox.information(self, "Geladen",
                                    f"Macros aus '{self.store.path}' geladen.")


# ---------------------------------------------------------------------------
# RttyBaseScreen  –  abstrakte Basisklasse
# ---------------------------------------------------------------------------

class RttyBaseScreen(QWidget):
    """Gemeinsames Layout für Baudot- und ASCII-RTTY-Screens.

    Unterklassen MÜSSEN folgende Klassenattribute setzen:
        MODE_TITLE : str   — wird als Titel-Label angezeigt

    Unterklassen MÜSSEN folgende Methode implementieren:
        _build_mode_buttons(layout: QHBoxLayout) -> None
            Fügt die moduspezifischen Buttons in Reihe 2 ein.
            Die Methode ist verantwortlich für addStretch() am Ende.
    """

    # Unterklasse kann diese Attribute überschreiben
    MODE_TITLE:   str       = "RTTY"
    BAUD_LABEL:   str       = "RBAUD (Speed):"
    BAUD_VALUES:  list[str] = RBAUD_VALUES   # Default = Baudot-Werte aus Modul-Konstante

    def __init__(self, parent=None):
        super().__init__(parent)
        # MacroStore beim Start laden
        self._macro_store = MacroStore()
        err = self._macro_store.load()
        if err:
            print(f"[MacroStore] {err}")

        self._blink_phase = False
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(400)
        self._blink_timer.timeout.connect(self._on_blink_tick)

        # UTC-Uhr — aktualisiert jede Sekunde
        self._utc_timer = QTimer(self)
        self._utc_timer.setInterval(1000)
        self._utc_timer.timeout.connect(self._update_utc)
        self._utc_timer.start()

        self._build_ui()

        # Nach dem UI-Aufbau: TX-Fenster als dauerhaften Focus-Inhaber installieren.
        # installEventFilter(self) auf dem gesamten Fenster fängt alle
        # KeyPress-Events ab, die nicht von einem Eingabe-Widget konsumiert werden.
        self.installEventFilter(self)

        # Initialer Focus: TX-Fenster bekommt den Cursor sofort beim Öffnen.
        # singleShot(0) wartet einen Event-Loop-Durchlauf — erst dann ist das
        # Widget vollständig gerendert und setFocus() greift zuverlässig.
        QTimer.singleShot(0, lambda: self.tx_input.setFocus())

    # ------------------------------------------------------------------
    # Hilfsmethode: Button ohne Focus-Raub erzeugen
    # ------------------------------------------------------------------

    @staticmethod
    def _no_focus_btn(label: str, width: int | None = None,
                      height: int | None = None,
                      checkable: bool = False) -> QPushButton:
        """Erzeugt einen QPushButton mit NoFocus-Policy.

        NoFocus bedeutet: Ein Mausklick aktiviert den Button, gibt ihm
        aber KEINEN Keyboard-Focus.  Der Cursor im TX-Fenster bleibt
        dadurch immer aktiv – Tastendrücke landen sofort als TX-Eingabe.

        Verwendung:
            btn = self._no_focus_btn("STBY", width=BTN_W)
        """
        btn = QPushButton(label)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if width is not None:
            btn.setFixedWidth(width)
        if height is not None:
            btn.setFixedHeight(height)
        if checkable:
            btn.setCheckable(True)
        return btn

    # ------------------------------------------------------------------
    # Event-Filter: leitet Tastendrücke ans TX-Fenster weiter
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """Sicherheitsnetz: jeder Tastendruck landet im TX-Fenster.

        Wird ein KeyPress-Event von einem Widget ausgelöst, das KEIN
        Texteingabe-Widget ist (QTextEdit / QLineEdit), leiten wir das
        Event direkt ans TX-Fenster weiter.

        Das greift auch dann, wenn ein Button versehentlich doch Focus
        bekommen hat (z.B. per Tab-Taste).
        """
        if event.type() == QEvent.Type.KeyPress:
            focused = self.focusWidget()
            # Wenn der Focus bereits in einem Eingabefeld ist → normal weiter
            if isinstance(focused, (QTextEdit, QLineEdit)):
                return super().eventFilter(obj, event)
            # Sonst: Event ans TX-Fenster schicken, falls vorhanden
            if hasattr(self, "tx_input") and self.tx_input is not None:
                self.tx_input.setFocus()
                # Event an das TX-Fenster weiterleiten
                from PyQt6.QtWidgets import QApplication
                QApplication.sendEvent(self.tx_input, event)
                return True   # Event als behandelt markieren
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # UI-Aufbau  (einmalig beim Initialisieren)
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        # Titelzeile: Modusname links, UTC-Zeit rechts
        title_row = QHBoxLayout()
        title = QLabel(self.MODE_TITLE)
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        self.lbl_utc = QLabel()
        self.lbl_utc.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        self.lbl_utc.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._update_utc()   # Sofort befüllen, nicht erst nach 1 Sekunde warten
        title_row.addWidget(self.lbl_utc)
        root.addLayout(title_row)

        add_hline(root)

        # Baud-Parameter (Label und Werte kommen vom Klassenattribut der Unterklasse)
        param_row = QHBoxLayout()
        param_row.setSpacing(8)
        lbl = QLabel(self.BAUD_LABEL)
        lbl.setFixedWidth(110)
        param_row.addWidget(lbl)
        self.combo_rbaud = QComboBox()
        self.combo_rbaud.addItems(self.BAUD_VALUES)
        self.combo_rbaud.setCurrentText("45")
        self.combo_rbaud.setFixedWidth(80)
        param_row.addWidget(self.combo_rbaud)
        param_row.addStretch()
        root.addLayout(param_row)

        add_hline(root)

        # Reihe 1: SEND / RECEIVE (prominent)
        row1 = QHBoxLayout()
        row1.setSpacing(SPACING)

        self.btn_send = QPushButton("Send")
        self.btn_send.setFixedWidth(PROM_W)
        self.btn_send.setFixedHeight(46)
        self.btn_send.setCheckable(True)
        self.btn_send.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # kein Focus-Raub
        self.btn_send.setStyleSheet(STYLE_PROM_INACTIVE)
        self.btn_send.toggled.connect(self._on_send_toggled)

        self.btn_receive = QPushButton("Receive")
        self.btn_receive.setFixedWidth(PROM_W)
        self.btn_receive.setFixedHeight(46)
        self.btn_receive.setCheckable(True)
        self.btn_receive.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # kein Focus-Raub
        self.btn_receive.setStyleSheet(STYLE_PROM_INACTIVE)
        self.btn_receive.toggled.connect(self._on_receive_toggled)

        row1.addWidget(self.btn_send)
        row1.addWidget(self.btn_receive)
        row1.addStretch()
        root.addLayout(row1)

        # Reihe 2: moduspezifische Buttons — von Unterklasse befüllt
        row2 = QHBoxLayout()
        row2.setSpacing(SPACING)
        self._build_mode_buttons(row2)   # ← Unterklasse überschreibt das
        root.addLayout(row2)

        add_hline(root)

        # RX-Fenster
        self.rx_display = QTextEdit()
        self.rx_display.setReadOnly(True)
        self.rx_display.setFont(QFont("Courier New", 10))
        self.rx_display.setPlaceholderText("RX – empfangene Zeichen erscheinen hier …")
        self.rx_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        style_rx_widget(self.rx_display)
        root.addWidget(self.rx_display, stretch=1)

        add_hline(root)

        # TX-Fenster (5 Zeilen)
        self.tx_input = QTextEdit()
        self.tx_input.setFont(QFont("Courier New", 10))
        self.tx_input.setPlaceholderText("TX – Eingabe hier …")
        fm   = self.tx_input.fontMetrics()
        mc   = self.tx_input.contentsMargins()
        self.tx_input.setFixedHeight(
            fm.lineSpacing() * 5 + mc.top() + mc.bottom() + 8
        )
        style_tx_widget(self.tx_input)
        root.addWidget(self.tx_input)

        add_hline(root)

        # Macro-Sektion
        macro_row = QHBoxLayout()
        macro_row.setSpacing(SPACING)

        self.macro_buttons: list[QPushButton] = []
        for i in range(MACRO_COUNT):
            btn = QPushButton(self._macro_store.names[i])
            btn.setFixedWidth(BTN_W)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # kein Focus-Raub
            macro_row.addWidget(btn)
            self.macro_buttons.append(btn)

        macro_row.addStretch()

        self.btn_edit_macros = QPushButton("Edit Macros")
        self.btn_edit_macros.setFixedWidth(BTN_W + 20)
        self.btn_edit_macros.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # kein Focus-Raub
        self.btn_edit_macros.setStyleSheet(
            "QPushButton { border: 1px solid #666; border-radius: 4px; padding: 4px; }"
        )
        self.btn_edit_macros.clicked.connect(self._on_edit_macros)
        macro_row.addWidget(self.btn_edit_macros)
        root.addLayout(macro_row)

    # ------------------------------------------------------------------
    # Abstrakte Methode — MUSS von Unterklasse überschrieben werden
    # ------------------------------------------------------------------

    def _build_mode_buttons(self, layout: QHBoxLayout) -> None:
        """Baut die moduspezifischen Buttons in Reihe 2.

        Unterklasse fügt ihre Buttons in 'layout' ein und ruft am Ende
        layout.addStretch() auf.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} muss _build_mode_buttons() implementieren."
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_send_toggled(self, checked: bool) -> None:
        if not checked:
            return   # already active — ignore re-click
        if checked:
            self.btn_receive.blockSignals(True)
            self.btn_receive.setChecked(False)
            self.btn_receive.blockSignals(False)
            self.btn_receive.setStyleSheet(STYLE_PROM_INACTIVE)
            self._blink_phase = True
            self.btn_send.setStyleSheet(STYLE_SEND_ON)
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self.btn_send.setStyleSheet(STYLE_PROM_INACTIVE)

    def _on_receive_toggled(self, checked: bool) -> None:
        if not checked:
            return   # already active — ignore re-click
        if checked:
            self._blink_timer.stop()
            self.btn_send.blockSignals(True)
            self.btn_send.setChecked(False)
            self.btn_send.blockSignals(False)
            self.btn_send.setStyleSheet(STYLE_PROM_INACTIVE)
            self.btn_receive.setStyleSheet(STYLE_RECEIVE_ON)
        else:
            self.btn_receive.setStyleSheet(STYLE_PROM_INACTIVE)

    def _on_blink_tick(self) -> None:
        self._blink_phase = not self._blink_phase
        self.btn_send.setStyleSheet(
            STYLE_SEND_BLINK if self._blink_phase else STYLE_SEND_ON
        )

    def _update_utc(self) -> None:
        """Aktualisiert das UTC-Zeit-Label auf die aktuelle Sekunde."""
        now = datetime.now(timezone.utc)
        self.lbl_utc.setText(now.strftime("UTC  %H:%M:%S"))

    def _on_edit_macros(self) -> None:
        dlg = MacroEditDialog(self._macro_store, parent=self)
        dlg.exec()
        for i, btn in enumerate(self.macro_buttons):
            btn.setText(self._macro_store.names[i])
