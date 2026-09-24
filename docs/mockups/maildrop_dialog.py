"""
maildrop_dialog.py  -  MailDrop session window - PK232PY mockup v2

Why this is a SESSION and not just a dialog
-------------------------------------------
Local mailbox administration uses MDCHECK, and the manual (STABO ch. 5 and
ch. 12) is explicit about two things:

  * MDCHECK only works while the PK-232 is NOT connected to any packet or
    AMTOR station
  * while logged in locally, the TNC answers every incoming connect with a
    BUSY frame

Measured on the hardware (2026-09-22/23): MDCHECK has no Host Mode mnemonic
(mdcheck_scan probed all 23 M? candidates, no hit), so the session runs over
the verbose path:

    Host Mode  ->  verbose  ->  MDCHECK  ->  [session]  ->  B  ->  Host Mode

Both transitions already exist as proven state machines in the app. The
window therefore owns a lifecycle, shows what it costs while it runs, and
always offers a way back.

Remote access (MAILDROP ON) is a different matter and DOES run alongside
normal operation - but only if the mailbox has its own callsign in MYMAIL.

Second reason this window matters: the PK-232 has no RAM buffer battery
(confirmed 2026-09-22), so every message is lost at power-off. The local
archive is not a convenience, it is the only durable store.

Protocol facts used below (all measured, see CLAUDE.md):
  prompt   (AEA PK-232M)  18536 free  (B,E,K,L,R,S) >
  empty    *** Message not found.
  list     Msg#    Size To     From   @ BBS  Date       Time   Title
             1 PN    36 OE3GAS OE3GAS        22-Sep-26  18:00  test 1
  status   type P/T/B + read flag N/Y
  send     S <call> [@ BBS] [< FROM]  ->  Subject:  ->  text  ->  /EX
  kill     K <n>  ->  *** Done.
  leave    B      ->  cmd:

Launch:
    python maildrop_dialog.py
    python maildrop_dialog.py --shot=session.png
    python maildrop_dialog.py --gate-shot=gate.png
    python maildrop_dialog.py --compose-shot=compose.png
"""

import sys
from dataclasses import dataclass

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSplitter, QTreeWidget, QTreeWidgetItem, QTextEdit,
    QCheckBox, QFrame, QLineEdit, QDialogButtonBox, QGridLayout,
    QHeaderView, QMessageBox, QStackedWidget,
)

from opmode_rtty_base import apply_app_style, get_theme, add_hline

FONT_UI = "Segoe UI"
FONT_MONO = "Courier New"

# Session lifecycle
S_CLOSED = "closed"     # not logged in, preconditions shown
S_ACTIVE = "active"     # logged in, packet operation suspended

# Where a message lives
WHERE_BOTH = "both"
WHERE_TNC = "tnc"
WHERE_ARCHIVE = "archive"

_WHERE_TEXT = {
    WHERE_BOTH: "TNC + archive",
    WHERE_TNC: "TNC only",
    WHERE_ARCHIVE: "archive only",
}
_WHERE_TIP = {
    WHERE_BOTH: "Stored in the TNC and saved in the local archive.",
    WHERE_TNC: "Only in the TNC's RAM - lost at power-off unless synced.",
    WHERE_ARCHIVE: "Only in the local archive - the TNC lost it at "
                   "power-off. 'Restore to TNC' writes it back.",
}
_WHERE_COLOR = {
    WHERE_BOTH: "#66dd88",
    WHERE_TNC: "#e8b23a",
    WHERE_ARCHIVE: "#7d8c99",
}

_TYPE_TEXT = {"P": "Personal", "T": "Traffic", "B": "Bulletin"}

_BTN = (
    "QPushButton { background-color: #445566; color: #ffffff;"
    " border: 1px solid #334455; border-radius: 4px; padding: 5px 10px; }"
    "QPushButton:hover { background-color: #556677; }"
    "QPushButton:disabled { background-color: #333d47; color: #6d7d8c; }"
)
_BTN_PRIMARY = (
    "QPushButton { background-color: #2a6496; color: #ffffff;"
    " border: 1px solid #1a4476; border-radius: 4px; padding: 6px 14px;"
    " font-weight: bold; }"
    "QPushButton:hover { background-color: #3474aa; }"
    "QPushButton:disabled { background-color: #333d47; color: #6d7d8c; }"
)
_BTN_DANGER = (
    "QPushButton { background-color: #6a3434; color: #ffffff;"
    " border: 1px solid #4a2424; border-radius: 4px; padding: 5px 10px; }"
    "QPushButton:hover { background-color: #804040; }"
    "QPushButton:disabled { background-color: #333d47; color: #6d7d8c; }"
)
_BTN_END = (
    "QPushButton { background-color: #8a6a1e; color: #ffffff;"
    " border: 1px solid #6a4a0e; border-radius: 4px; padding: 6px 14px;"
    " font-weight: bold; }"
    "QPushButton:hover { background-color: #a07a2a; }"
)


def _muted() -> str:
    return "#8fa0ae"


def _btn(text: str, tip: str = "", style: str = _BTN,
         width: int | None = None) -> QPushButton:
    b = QPushButton(text)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setFont(QFont(FONT_UI, 8))
    b.setStyleSheet(style)
    if tip:
        b.setToolTip(tip)
    if width:
        b.setFixedWidth(width)
    return b


def _vsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    f.setFixedHeight(24)
    return f


# ---------------------------------------------------------------------------
# Data (mockup)
# ---------------------------------------------------------------------------

@dataclass
class MailMessage:
    number: str
    mtype: str      # P | T | B
    read: str       # N | Y
    size: int
    to: str
    frm: str
    bbs: str
    date: str       # "22-Sep-26  18:00", empty when the TNC clock was unset
    subject: str
    body: str
    where: str


DEMO_MESSAGES = [
    MailMessage("1", "P", "Y", 44, "OE3GAS", "DL1ABC", "", "22-Sep-26  18:00",
                "Sked Sunday 80 m",
                "Hallo Gerhard,\n\nwie besprochen Sonntag 08:00 UTC auf "
                "3.583, 300 Bd HF-Packet.\nIch rufe dich auf Kanal 1.\n\n"
                "73 de Franz", WHERE_BOTH),
    MailMessage("2", "P", "N", 41, "OE3GAS", "DK3WX", "DB0MUC",
                "22-Sep-26  18:18", "PK-232 firmware v7.1 question",
                "Hi OE3GAS,\n\nkurze Frage zur v7.1: laeuft PASSALL im Host "
                "Mode bei dir ueber PX?\n\nvy 73 Dieter", WHERE_TNC),
    MailMessage("3", "B", "N", 52, "ALL", "OE3XNR", "OE3XNR",
                "22-Sep-26  18:19", "Repeater OE3XNR maintenance",
                "Das Relais OE3XNR ist am Samstag zwischen 09:00 und 13:00 "
                "UTC wegen Wartung abgeschaltet.", WHERE_TNC),
    MailMessage("4", "T", "N", 33, "OE5XYZ", "OE3GAS", "", "22-Sep-26  18:20",
                "QSL via bureau",
                "QSL fuer das QSO vom 20.09. geht ueber das Buero.",
                WHERE_BOTH),
    MailMessage("-", "P", "Y", 37, "OE3GAS", "OE1KBC", "", "18-Sep-26  20:11",
                "Antenna test results",
                "Die Messwerte vom Dipol: SWR 1.3 auf 3.58.\n73 de Kurt",
                WHERE_ARCHIVE),
    MailMessage("-", "P", "Y", 30, "OE3GAS", "OE5REO", "", "17-Sep-26  16:45",
                "Re: HF packet frequency",
                "Wir sind meistens auf 14.105 LSB, 300 Bd.\nvy 73",
                WHERE_ARCHIVE),
]


# ---------------------------------------------------------------------------
# Compose dialog
# ---------------------------------------------------------------------------

class MailComposeDialog(QDialog):
    """New message (or reply). Mirrors the measured S command."""

    def __init__(self, reply_to: MailMessage | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New MailDrop message" if reply_to is None
                            else "Reply")
        self.setMinimumSize(600, 470)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        def lbl(t: str) -> QLabel:
            w = QLabel(t)
            w.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
            w.setStyleSheet(f"color: {_muted()};")
            return w

        self.le_to = QLineEdit(reply_to.frm if reply_to else "")
        self.le_to.setFont(QFont(FONT_MONO, 10))
        self.le_to.setPlaceholderText("OE1XYZ")
        self.le_to.setFixedWidth(130)

        self.le_bbs = QLineEdit(reply_to.bbs if reply_to else "")
        self.le_bbs.setFont(QFont(FONT_MONO, 10))
        self.le_bbs.setFixedWidth(130)
        self.le_bbs.setPlaceholderText("DB0MUC")
        self.le_bbs.setToolTip("Home BBS of the recipient - sent as '@ BBS'.")

        self.le_from = QLineEdit()
        self.le_from.setFont(QFont(FONT_MONO, 10))
        self.le_from.setFixedWidth(130)
        self.le_from.setPlaceholderText("MYCALL")
        self.le_from.setToolTip(
            "Sender. The SysOp may set a foreign callsign - sent as '< FROM'.\n"
            "Used when restoring archived messages to the TNC.")

        self.cb_type = QComboBox()
        self.cb_type.addItems(["Personal (S)", "Traffic (ST)", "Bulletin (SB)"])
        self.cb_type.setFixedWidth(130)

        self.le_subject = QLineEdit(
            ("Re: " + reply_to.subject) if reply_to else "")
        self.le_subject.setFont(QFont(FONT_UI, 9))

        grid.addWidget(lbl("To"), 0, 0)
        grid.addWidget(self.le_to, 0, 1)
        grid.addWidget(lbl("@ BBS"), 0, 2)
        grid.addWidget(self.le_bbs, 0, 3)
        grid.addWidget(lbl("Type"), 1, 0)
        grid.addWidget(self.cb_type, 1, 1)
        grid.addWidget(lbl("From"), 1, 2)
        grid.addWidget(self.le_from, 1, 3)
        grid.addWidget(lbl("Subject"), 2, 0)
        grid.addWidget(self.le_subject, 2, 1, 1, 3)
        grid.setColumnStretch(4, 1)
        root.addLayout(grid)

        self.te_body = QTextEdit()
        self.te_body.setFont(QFont(FONT_MONO, 10))
        self.te_body.setPlaceholderText("Message text ...")
        if reply_to:
            quoted = "\n".join("> " + l for l in reply_to.body.splitlines())
            self.te_body.setPlainText(f"\n\n{quoted}")
        root.addWidget(self.te_body, stretch=1)

        self.lbl_check = QLabel()
        self.lbl_check.setFont(QFont(FONT_UI, 8))
        self.lbl_check.setWordWrap(True)
        root.addWidget(self.lbl_check)

        box = QDialogButtonBox()
        self.btn_send = box.addButton("Send to MailDrop",
                                      QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_send.setStyleSheet(_BTN_PRIMARY)
        box.addButton(QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        root.addWidget(box)

        self.te_body.textChanged.connect(self._validate)
        self._validate()

    def _validate(self) -> None:
        """Two rules that come straight from the hardware measurements.

        1. A line starting with /EX ends the transfer at the TNC - such a
           message would be cut off in the middle.
        2. Non-ASCII is lost on the serial link (measured: 'fuer' arrived
           as 'f?r'), so umlauts are transliterated before sending.
        """
        text = self.te_body.toPlainText()
        bad_line = any(l.strip().upper().startswith("/EX")
                       for l in text.splitlines())
        non_ascii = any(ord(c) > 127 for c in text)

        if bad_line:
            self.lbl_check.setText(
                "A line starting with /EX would end the message early - "
                "please rephrase that line.")
            self.lbl_check.setStyleSheet("color: #d05a5a;")
        elif non_ascii:
            self.lbl_check.setText(
                "Contains non-ASCII characters - they will be transliterated "
                "(ue, oe, ae, ss) before sending.")
            self.lbl_check.setStyleSheet("color: #e8b23a;")
        else:
            self.lbl_check.setText(f"{len(text)} characters")
            self.lbl_check.setStyleSheet(f"color: {_muted()};")
        self.btn_send.setEnabled(not bad_line)


# ---------------------------------------------------------------------------
# MailDrop session window
# ---------------------------------------------------------------------------

class MailDropDialog(QDialog):

    COLS = ["#", "Type", "St", "Where", "To", "From", "@ BBS", "Date",
            "Size", "Title"]

    def __init__(self, state: str = S_ACTIVE, channel_busy: bool = False,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("MailDrop - OE3GAS")
        self.resize(1000, 690)
        self._messages = list(DEMO_MESSAGES)
        self._state = state
        self._channel_busy = channel_busy     # a packet channel is connected
        self._mymail_set = False              # MYMAIL is 'none' on this TNC
        self._free = 18284

        self._build_ui()
        self._apply_state()

    # -- UI ----------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        root.addLayout(self._build_header())
        root.addWidget(self._build_banner())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_gate_page())     # 0
        self.stack.addWidget(self._build_session_page())  # 1
        root.addWidget(self.stack, stretch=1)

        add_hline(root)
        root.addLayout(self._build_footer())

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        title = QLabel('<span style="font-size:12pt; font-weight:bold;">'
                       'MailDrop</span>')
        row.addWidget(title)

        call = QLabel("OE3GAS")
        call.setFont(QFont(FONT_MONO, 10, QFont.Weight.Bold))
        call.setToolTip("MYCALL - the mailbox answers under MYMAIL once set")
        row.addWidget(call)

        row.addStretch()

        self.lbl_free = QLabel()
        self.lbl_free.setFont(QFont(FONT_MONO, 9))
        self.lbl_free.setStyleSheet(f"color: {_muted()};")
        row.addWidget(self.lbl_free)

        self.lbl_dot = QLabel("·")
        self.lbl_dot.setStyleSheet(f"color: {_muted()};")
        row.addWidget(self.lbl_dot)

        self.lbl_counts = QLabel()
        self.lbl_counts.setFont(QFont(FONT_UI, 9, QFont.Weight.Bold))
        row.addWidget(self.lbl_counts)
        return row

    def _build_banner(self) -> QLabel:
        """One line that says what the session costs while it runs."""
        self.banner = QLabel()
        self.banner.setFont(QFont(FONT_UI, 9, QFont.Weight.Bold))
        self.banner.setWordWrap(True)
        self.banner.setContentsMargins(10, 6, 10, 6)
        return self.banner

    # -- gate page ---------------------------------------------------

    def _build_gate_page(self) -> QFrame:
        page = QFrame()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 14, 0, 0)
        lay.setSpacing(10)

        intro = QLabel(
            "Local mailbox administration logs the TNC into its own MailDrop "
            "(MDCHECK). While the session runs, packet operation is suspended "
            "and stations trying to connect receive a BUSY frame.")
        intro.setWordWrap(True)
        intro.setFont(QFont(FONT_UI, 9))
        lay.addWidget(intro)

        self.check_box = QVBoxLayout()
        self.check_box.setSpacing(6)
        lay.addLayout(self.check_box)

        lay.addSpacing(6)
        row = QHBoxLayout()
        self.btn_open = _btn("Open MailDrop session", "", _BTN_PRIMARY, 200)
        self.btn_open.setFont(QFont(FONT_UI, 9, QFont.Weight.Bold))
        self.btn_open.clicked.connect(self._on_open)
        row.addWidget(self.btn_open)

        self.lbl_gate_hint = QLabel()
        self.lbl_gate_hint.setFont(QFont(FONT_UI, 8))
        self.lbl_gate_hint.setWordWrap(True)
        row.addWidget(self.lbl_gate_hint, stretch=1)
        lay.addLayout(row)

        lay.addStretch()

        note = QLabel(
            "Remote access is a different setting: with MAILDROP ON and a "
            "callsign in MYMAIL, other stations can leave messages while you "
            "keep working normally. That does not need this session.")
        note.setWordWrap(True)
        note.setFont(QFont(FONT_UI, 8))
        note.setStyleSheet(f"color: {_muted()};")
        lay.addWidget(note)
        return page

    def _fill_checks(self) -> None:
        while self.check_box.count():
            item = self.check_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # kind: "ok" | "block" (stops the session) | "info" (does not)
        checks = [
            ("ok" if not self._channel_busy else "block",
             "No packet channel connected",
             "Channel 3 is connected to OE3XYZ-9 - the TNC refuses MDCHECK "
             "while any packet or AMTOR station is connected. Disconnect "
             "first."),
            ("ok", "TNC in Host Mode, no file transfer running", ""),
            ("ok" if self._mymail_set else "info",
             "MYMAIL is set - only needed so OTHER stations can reach the "
             "mailbox",
             "MYMAIL is 'none'. Local administration works anyway; remote "
             "access does not."),
        ]
        marks = {"ok": "OK  ", "block": "--  ", "info": "i   "}
        colors = {"ok": "#66dd88", "block": "#e8b23a", "info": _muted()}
        for kind, text, why in checks:
            w = QLabel(marks[kind] + text +
                       (f"\n      {why}" if why else ""))
            w.setFont(QFont(FONT_UI, 9))
            w.setWordWrap(True)
            w.setStyleSheet(f"color: {colors[kind]};")
            self.check_box.addWidget(w)

    # -- session page ------------------------------------------------

    def _build_session_page(self) -> QFrame:
        page = QFrame()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        lay.addLayout(self._build_toolbar())

        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_list())
        split.addWidget(self._build_reader())
        split.setSizes([290, 230])
        lay.addWidget(split, stretch=1)
        return page

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        self.btn_sync = _btn("Sync to archive",
                             "Read every TNC message and store it in the "
                             "local archive")
        self.btn_restore = _btn("Restore to TNC",
                                "Write archive-only messages back into the "
                                "TNC, keeping sender, BBS and type")
        row.addWidget(self.btn_sync)
        row.addWidget(self.btn_restore)
        row.addWidget(_vsep())

        self.btn_new = _btn("New...", "Write a new message", _BTN_PRIMARY)
        self.btn_new.clicked.connect(lambda: self._compose(None))
        self.btn_reply = _btn("Reply", "Reply to the selected message")
        self.btn_reply.clicked.connect(lambda: self._compose(self._current()))
        self.btn_kill = _btn("Kill", "Delete the selected message", _BTN_DANGER)
        self.btn_kill.clicked.connect(self._on_kill)
        self.btn_header = _btn("Header...", "Edit status and callsigns (E)")
        self.btn_save = _btn("Save as...", "Save the message to a text file")
        for b in (self.btn_new, self.btn_reply, self.btn_kill,
                  self.btn_header, self.btn_save):
            row.addWidget(b)

        row.addStretch()

        lbl = QLabel("Show")
        lbl.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_muted()};")
        row.addWidget(lbl)
        self.cb_filter = QComboBox()
        self.cb_filter.addItems(["All", "Unread", "Personal", "Traffic",
                                 "Bulletins", "At risk (TNC only)",
                                 "Archive only"])
        self.cb_filter.setFixedWidth(150)
        self.cb_filter.currentIndexChanged.connect(self._fill_list)
        row.addWidget(self.cb_filter)
        return row

    def _build_list(self) -> QTreeWidget:
        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLS))
        self.tree.setHeaderLabels(self.COLS)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setFont(QFont(FONT_MONO, 9))
        hdr = self.tree.header()
        for i, w in enumerate([30, 64, 28, 100, 72, 72, 66, 130, 44]):
            hdr.resizeSection(i, w)
        hdr.setSectionResizeMode(len(self.COLS) - 1,
                                 QHeaderView.ResizeMode.Stretch)
        t = get_theme()
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background-color: {t['bg_input']};"
            f" alternate-background-color: #1f2b38;"
            f" border: 1px solid #2a3a4a; }}"
            "QTreeWidget::item:selected { background-color: #2a6496; }")
        self.tree.currentItemChanged.connect(self._on_select)
        return self.tree

    def _build_reader(self) -> QFrame:
        frame = QFrame()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(4)

        self.lbl_head = QLabel()
        self.lbl_head.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_head.setFont(QFont(FONT_UI, 9))
        self.lbl_head.setWordWrap(True)
        lay.addWidget(self.lbl_head)

        self.reader = QTextEdit()
        self.reader.setReadOnly(True)
        self.reader.setFont(QFont(FONT_MONO, 10))
        t = get_theme()
        self.reader.setStyleSheet(
            f"QTextEdit {{ background-color: {t['bg_input']};"
            f" color: {t['rx_color']}; border: 1px solid #2a3a4a; }}")
        lay.addWidget(self.reader, stretch=1)
        return frame

    # -- footer ------------------------------------------------------

    def _build_footer(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(18)
        self.chk_save_exit = QCheckBox("Save archive on exit")
        self.chk_save_exit.setChecked(True)
        self.chk_save_exit.setToolTip(
            "Required on a PK-232 without buffer battery: the TNC mailbox is "
            "empty after every power-off.")
        self.chk_offer_restore = QCheckBox("Offer restore after TNC power-up")
        self.chk_offer_restore.setChecked(True)
        self.chk_offer_restore.setToolTip(
            "When the TNC comes up in factory state (MYCALL PK232), ask "
            "whether to write the archive back.")
        row.addWidget(self.chk_save_exit)
        row.addWidget(self.chk_offer_restore)
        row.addStretch()

        self.btn_end = _btn("End session", "Send B and return to Host Mode",
                            _BTN_END, 150)
        self.btn_end.setFont(QFont(FONT_UI, 9, QFont.Weight.Bold))
        self.btn_end.clicked.connect(self._on_end)
        row.addWidget(self.btn_end)

        self.btn_close = _btn("Close", width=90)
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close)
        col.addLayout(row)

        self.lbl_footer = QLabel()
        self.lbl_footer.setFont(QFont(FONT_UI, 8))
        self.lbl_footer.setStyleSheet(f"color: {_muted()};")
        col.addWidget(self.lbl_footer)
        return col

    # -- state -------------------------------------------------------

    def _apply_state(self) -> None:
        active = self._state == S_ACTIVE
        self.stack.setCurrentIndex(1 if active else 0)

        if active:
            self.banner.setText(
                "MailDrop session active   ·   packet operation is "
                "suspended   ·   incoming connects receive BUSY")
            self.banner.setStyleSheet(
                "background-color: #8a6a1e; color: #ffffff;"
                " border: 1px solid #6a4a0e; border-radius: 4px;")
            self.lbl_footer.setText(
                "Archive: E:\\PK232\\maildrop_archive.json     last saved "
                "14:22 UTC     'End session' sends B and returns the TNC to "
                "Host Mode.")
        else:
            self.banner.setText(
                "Session closed   ·   normal packet operation")
            self.banner.setStyleSheet(
                "background-color: #24313d; color: #9fb4c4;"
                " border: 1px solid #2a3a4a; border-radius: 4px;")
            self.lbl_footer.setText(
                "Archive: E:\\PK232\\maildrop_archive.json     6 messages"
                "     last saved 14:22 UTC")
            self._fill_checks()
            can_open = not self._channel_busy
            self.btn_open.setEnabled(can_open)
            self.lbl_gate_hint.setText(
                "" if can_open else
                "Disconnect channel 3 first - the TNC refuses MDCHECK while "
                "a station is connected.")
            self.lbl_gate_hint.setStyleSheet(
                f"color: {'#e8b23a' if not can_open else _muted()};")

        self.btn_end.setVisible(active)
        self.lbl_free.setText(f"{self._free} bytes free" if active else "")
        self.lbl_dot.setVisible(active)

        self._fill_list()
        self._update_counts()
        if active and self.tree.topLevelItemCount() > 1:
            self.tree.setCurrentItem(self.tree.topLevelItem(1))

    # -- data --------------------------------------------------------

    def _visible(self, m: MailMessage) -> bool:
        f = self.cb_filter.currentText()
        if f == "Unread":
            return m.read == "N"
        if f == "Personal":
            return m.mtype == "P"
        if f == "Traffic":
            return m.mtype == "T"
        if f == "Bulletins":
            return m.mtype == "B"
        if f.startswith("At risk"):
            return m.where == WHERE_TNC
        if f == "Archive only":
            return m.where == WHERE_ARCHIVE
        return True

    def _fill_list(self) -> None:
        self.tree.clear()
        for m in self._messages:
            if not self._visible(m):
                continue
            it = QTreeWidgetItem([
                m.number, _TYPE_TEXT.get(m.mtype, m.mtype), m.read,
                _WHERE_TEXT[m.where], m.to, m.frm, m.bbs,
                m.date or "clock unset", str(m.size), m.subject])
            it.setData(0, Qt.ItemDataRole.UserRole, m)

            if m.where == WHERE_ARCHIVE:
                col = "#7d8c99"
            elif m.read == "N":
                col = "#ffffff"
            else:
                col = "#c8d4de"
            for c in range(len(self.COLS)):
                it.setForeground(c, QBrush(QColor(col)))
            it.setForeground(3, QBrush(QColor(_WHERE_COLOR[m.where])))
            it.setToolTip(3, _WHERE_TIP[m.where])
            if m.read == "N":
                for c in range(len(self.COLS)):
                    f = QFont(FONT_MONO, 9)
                    f.setBold(True)
                    it.setFont(c, f)
            self.tree.addTopLevelItem(it)

    def _update_counts(self) -> None:
        if self._state != S_ACTIVE:
            # Not logged in - the TNC side is simply unknown, so do not
            # pretend to know it.
            arch = len(self._messages)
            self.lbl_counts.setText(f"Archive {arch}")
            self.lbl_counts.setStyleSheet("color: #d0e4f4;")
            return
        tnc = sum(1 for m in self._messages if m.where != WHERE_ARCHIVE)
        arch = sum(1 for m in self._messages if m.where != WHERE_TNC)
        risk = sum(1 for m in self._messages if m.where == WHERE_TNC)
        self.lbl_counts.setText(
            f"TNC {tnc}   ·   Archive {arch}" +
            (f"   ·   {risk} at risk" if risk else ""))
        self.lbl_counts.setStyleSheet(
            "color: #e8b23a;" if risk else "color: #d0e4f4;")

    def _current(self) -> MailMessage | None:
        it = self.tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    # -- slots -------------------------------------------------------

    def _on_open(self) -> None:
        self._state = S_ACTIVE
        self._apply_state()

    def _on_end(self) -> None:
        self._state = S_CLOSED
        self._apply_state()

    def _on_select(self, cur, _prev) -> None:
        m = cur.data(0, Qt.ItemDataRole.UserRole) if cur else None
        has = m is not None
        in_tnc = has and m.where != WHERE_ARCHIVE
        self.btn_reply.setEnabled(has)
        self.btn_kill.setEnabled(has)
        self.btn_header.setEnabled(in_tnc)
        self.btn_save.setEnabled(has)
        if not has:
            self.lbl_head.clear()
            self.reader.clear()
            return
        bbs = f" @ {m.bbs}" if m.bbs else ""
        where = (f'<span style="color:{_WHERE_COLOR[m.where]};">'
                 f'{_WHERE_TEXT[m.where]}</span>')
        self.lbl_head.setText(
            f'<b>{m.subject}</b><br>'
            f'<span style="color:{_muted()};">From</span> {m.frm}{bbs}'
            f'&nbsp;&nbsp;<span style="color:{_muted()};">To</span> {m.to}'
            f'&nbsp;&nbsp;<span style="color:{_muted()};">Date</span> '
            f'{m.date or "clock unset"}'
            f'&nbsp;&nbsp;<span style="color:{_muted()};">Msg</span> '
            f'{m.number}&nbsp;&nbsp;{_TYPE_TEXT.get(m.mtype, m.mtype)}'
            f'&nbsp;&nbsp;{where}')
        self.reader.setPlainText(m.body)

    def _compose(self, reply_to: MailMessage | None) -> None:
        MailComposeDialog(reply_to, self).exec()

    def _on_kill(self) -> None:
        m = self._current()
        if m is None:
            return
        where = {
            WHERE_BOTH: "from the TNC and from the local archive",
            WHERE_TNC: "from the TNC",
            WHERE_ARCHIVE: "from the local archive",
        }[m.where]
        QMessageBox.question(self, "Kill message",
                             f"Delete message '{m.subject}' {where}?")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

def main() -> None:
    shot = gate_shot = compose_shot = ""
    for arg in sys.argv[1:]:
        if arg.startswith("--shot="):
            shot = arg.split("=", 1)[1]
        elif arg.startswith("--gate-shot="):
            gate_shot = arg.split("=", 1)[1]
        elif arg.startswith("--compose-shot="):
            compose_shot = arg.split("=", 1)[1]

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_app_style(app, "dark")

    if compose_shot:
        dlg = MailComposeDialog(DEMO_MESSAGES[1])
        dlg.le_from.setText("OE3GAS")
        dlg.te_body.setPlainText(
            "Hallo Dieter,\n\nja, PASSALL laeuft im Host Mode ueber PX, "
            "nicht PS.\nAm 21.09. am Geraet bestaetigt.\n\n73 de Gerhard")
        dlg.show()
        QTimer.singleShot(500, lambda: (dlg.grab().save(compose_shot),
                                        app.quit()))
        sys.exit(app.exec())

    if gate_shot:
        dlg = MailDropDialog(state=S_CLOSED, channel_busy=True)
        dlg.show()
        QTimer.singleShot(500, lambda: (dlg.grab().save(gate_shot),
                                        app.quit()))
        sys.exit(app.exec())

    dlg = MailDropDialog(state=S_ACTIVE)
    dlg.show()
    if shot:
        QTimer.singleShot(600, lambda: (dlg.grab().save(shot), app.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()