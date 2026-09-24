# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop session window (P39).

Why a modal DIALOG, not an entry in the opmode ComboBox
--------------------------------------------------------
MailDrop is not a TNC operating mode — it is a SESSION within Packet
operation. MDCHECK does not switch the TNC's mode; it logs the TNC into
its own mailbox over the verbose-mode link while Packet stays "the
mode" the whole time (CLAUDE.md "MailDrop session"; MDCHECK has no Host
Mode mnemonic at all, see docs/P26_MDCHECK_Mnemonic_Spec.md). Giving it
a ComboBox entry would burden the mode-switch state machine
(OPMODE_SWITCH_STATE_MACHINE.md) with something that is not a mode, and
raise the question of what a mode switch means while a mailbox session
is running — a question that does not need to exist if MailDrop is
simply a dialog Packet operation opens and closes around, never a
destination the mode switch itself has to know about.

State handling (CLAUDE.md "two truths" rule)
---------------------------------------------
This dialog NEVER reads MailDropSession.state (the plain attribute).
Every redraw is driven by the state_changed signal's own delivered
value, cached in self._state purely for rendering — the same value the
signal handed over, never re-derived by polling the session afterwards.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QSplitter, QStackedWidget, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ...maildrop import (
    ArchivedMessage, MailDropArchive, MailDropEntry, MailDropSession,
    SerialManagerChannel, open_archive,
)
from ...maildrop import protocol as maildrop_protocol
from ..screens.macro_store import add_hline
from ..screens.ui_theme import get_theme

logger = logging.getLogger(__name__)

FONT_UI = "Segoe UI"
FONT_MONO = "Courier New"

# Where a message lives — computed from a header-field match against the
# local archive (P39), never the TNC's own message number, which is only
# unique within one power-on period (CLAUDE.md).
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
_TYPE_LETTERS = ["P", "T", "B"]

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
    "QPushButton:disabled { background-color: #333d47; color: #6d7d8c; }"
)


def _muted() -> str:
    return "#8fa0ae"


def _btn(text: str, tip: str = "", style: str = _BTN,
         width: Optional[int] = None) -> QPushButton:
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


def _header_key(mtype: str, to: str, frm: str, bbs: str, subject: str,
                 size: int) -> tuple:
    """Display-only match key for the 'Where' column (P39) — NOT
    archive.py's real duplicate-detection fingerprint, which also hashes
    the body text. A listing has no body (only read() gets one), so this
    compares only the header fields a listing DOES carry. Good enough to
    colour a row; a genuine collision here only affects which badge a row
    gets, never what add()/missing_in_tnc() decide when a message is
    actually archived.
    """
    return (mtype, to.strip().upper(), frm.strip().upper(),
            bbs.strip().upper(), subject, size)


@dataclass
class _Row:
    """One line of the unified TNC + archive list (P39)."""
    tnc_number: Optional[int]
    archive_id: Optional[int]
    mtype: str
    read: bool
    to: str
    frm: str
    bbs: str
    stamp: Optional[str]
    size: int
    subject: str
    body: Optional[str]   # None until read() delivers it (TNC-only rows)
    where: str


# ---------------------------------------------------------------------------
# Compose dialog
# ---------------------------------------------------------------------------

class MailComposeDialog(QDialog):
    """New message (or reply). Fields map straight onto
    maildrop.protocol.build_send_command() — nothing is assembled here."""

    def __init__(self, reply_to: Optional[_Row] = None, parent=None) -> None:
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
        if reply_to is not None:
            self.cb_type.setCurrentIndex(
                _TYPE_LETTERS.index(reply_to.mtype)
                if reply_to.mtype in _TYPE_LETTERS else 0
            )
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
        if reply_to and reply_to.body:
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
        """Two rules straight from maildrop.protocol, never reimplemented
        here (P39.4): check_body() rejects a line starting with /EX (it
        would end the transfer early at the TNC); sanitize_body() shows
        what non-ASCII characters would be transliterated to before the
        session itself does the same thing on send()."""
        text = self.te_body.toPlainText()
        reasons = maildrop_protocol.check_body(text)
        _clean, changes = maildrop_protocol.sanitize_body(text)

        if reasons:
            self.lbl_check.setText(
                "A line starting with /EX would end the message early - "
                "please rephrase that line.")
            self.lbl_check.setStyleSheet("color: #d05a5a;")
        elif changes:
            self.lbl_check.setText(
                "Contains non-ASCII characters - they will be transliterated "
                "(ue, oe, ae, ss) before sending.")
            self.lbl_check.setStyleSheet("color: #e8b23a;")
        else:
            self.lbl_check.setText(f"{len(text)} characters")
            self.lbl_check.setStyleSheet(f"color: {_muted()};")
        self.btn_send.setEnabled(not reasons)

    def get_send_args(self) -> dict:
        """Raw fields for MailDropSession.send() — sanitize_body() and
        check_body() run again inside the session itself; nothing is
        pre-processed here (P39.4: 'nichts selbst zusammensetzen')."""
        return dict(
            to=self.le_to.text().strip(),
            bbs=self.le_bbs.text().strip(),
            frm=self.le_from.text().strip(),
            mtype=_TYPE_LETTERS[self.cb_type.currentIndex()],
            subject=self.le_subject.text().strip(),
            body=self.te_body.toPlainText(),
        )


# ---------------------------------------------------------------------------
# MailDrop session window
# ---------------------------------------------------------------------------

class MailDropDialog(QDialog):

    COLS = ["#", "Type", "St", "Where", "To", "From", "@ BBS", "Date",
            "Size", "Title"]

    def __init__(
        self, serial_manager, channel_bar, mycall: str, maildrop_config,
        parent=None, session=None,
    ) -> None:
        """*serial_manager* is the app's connected SerialManager.
        *channel_bar* is the currently active Packet screen's ChannelBar
        (P39: the channel model already exists, never re-derived here).
        *maildrop_config* is AppConfig.maildrop (mymail, archive_*).

        *session*, when given, is used AS-IS instead of building a real
        MailDropSession/SerialManagerChannel — the seam
        test_maildrop_dialog.py uses to drive this dialog against a fake
        session (P39.6: "Sitzung gegen eine Attrappe von
        MailDropSession"), the same kind of injection seam
        SerialManager.set_port_factory() already uses elsewhere.
        """
        super().__init__(parent)
        self._serial = serial_manager
        self._channel_bar = channel_bar
        self._mycall = (mycall or "NOCALL").upper()
        self._md_config = maildrop_config
        self._device_release = getattr(serial_manager, 'tnc_release', None)

        self.setWindowTitle(f"MailDrop - {self._mycall}")
        self.resize(1000, 690)

        self._archive: Optional[MailDropArchive] = open_archive(maildrop_config)
        self._tnc_entries: list[MailDropEntry] = []
        self._rows: list[_Row] = []
        self._state = "CLOSED"
        self._pending_op: Optional[str] = None   # None|sync|restore|preview|kill
        self._sync_queue: list[int] = []
        self._restore_queue: list[ArchivedMessage] = []
        self._closing_confirmed = False
        self.last_have_mail: Optional[bool] = None   # P39.5, from prompt_info

        if session is not None:
            self.session = session
            self._wire_session_signals()
        else:
            self._build_session()
        self._build_ui()
        self._apply_state()

    # -- session wiring (P39.2 - signals only, never session.state) --------

    def _build_session(self) -> None:
        self._channel = SerialManagerChannel(self._serial)
        self.session = MailDropSession(self._channel, can_open=self._can_open)
        self._wire_session_signals()

    def _wire_session_signals(self) -> None:
        self.session.state_changed.connect(self._on_state_changed)
        self.session.prompt_info.connect(self._on_prompt_info)
        self.session.listing.connect(self._on_listing)
        self.session.message_read.connect(self._on_message_read)
        self.session.stored.connect(self._on_stored)
        self.session.killed.connect(self._on_killed)
        self.session.failed.connect(self._on_failed)

    def _can_open(self) -> tuple:
        """Fed to MailDropSession itself (checked again at the moment
        open() actually runs, since this dialog is modal but the Qt event
        loop keeps delivering background frames — a remote station could
        still connect while the gate page is showing)."""
        if not (self._serial.is_connected and self._serial.is_host_mode):
            return False, "The TNC is not connected in Host Mode."
        busy = self._channel_bar.channel_map() if self._channel_bar else {}
        if busy:
            call, ch = next(iter(busy.items()))
            return False, (
                f"Channel {ch} is connected to {call} - the TNC refuses "
                f"MDCHECK while any packet or AMTOR station is connected. "
                f"Disconnect first."
            )
        return True, ""

    # -- UI construction -----------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        root.addLayout(self._build_header())
        root.addWidget(self._build_banner())
        root.addLayout(self._build_progress_row())
        root.addLayout(self._build_status_row())

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

        call = QLabel(self._mycall)
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
        self.banner = QLabel()
        self.banner.setFont(QFont(FONT_UI, 9, QFont.Weight.Bold))
        self.banner.setWordWrap(True)
        self.banner.setContentsMargins(10, 6, 10, 6)
        return self.banner

    def _build_progress_row(self) -> QHBoxLayout:
        """OPENING/CLOSING (P39.3): an indeterminate bar plus the known
        step sequence — MailDropSession has no finer-grained signal than
        state_changed(OPENING/CLOSING) itself, so this shows what the
        session IS doing (its own documented step order), not a live
        per-step tracker that does not exist."""
        row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)   # indeterminate
        self.progress_bar.setFixedWidth(120)
        self.progress_bar.setFixedHeight(14)
        row.addWidget(self.progress_bar)
        self.lbl_progress = QLabel()
        self.lbl_progress.setFont(QFont(FONT_UI, 8))
        self.lbl_progress.setStyleSheet(f"color: {_muted()};")
        row.addWidget(self.lbl_progress, stretch=1)
        self._progress_row = row
        self._set_row_visible(row, False)
        return row

    def _build_status_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.lbl_status = QLabel()
        self.lbl_status.setFont(QFont(FONT_UI, 8))
        self.lbl_status.setWordWrap(True)
        row.addWidget(self.lbl_status, stretch=1)
        self.btn_retry = _btn("Retry", "Rebuild the session and try again",
                              _BTN_PRIMARY, 70)
        self.btn_retry.clicked.connect(self._on_retry_clicked)
        self.btn_retry.setVisible(False)
        row.addWidget(self.btn_retry)
        self._status_row = row
        return row

    @staticmethod
    def _set_row_visible(layout, visible: bool) -> None:
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w is not None:
                w.setVisible(visible)

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
        self.btn_open.clicked.connect(self.session.open)
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

        busy = self._channel_bar.channel_map() if self._channel_bar else {}
        channel_ok = not busy
        if not channel_ok:
            call, ch = next(iter(busy.items()))
            channel_why = (
                f"Channel {ch} is connected to {call} - the TNC refuses "
                f"MDCHECK while any packet or AMTOR station is connected. "
                f"Disconnect first."
            )
        else:
            channel_why = ""

        host_ok = self._serial.is_connected and self._serial.is_host_mode
        mymail_set = bool((self._md_config.mymail or "").strip())

        # kind: "ok" | "block" (stops the session) | "info" (does not)
        checks = [
            ("ok" if channel_ok else "block",
             "No packet channel connected", channel_why),
            ("ok" if host_ok else "block",
             "TNC in Host Mode",
             "" if host_ok else "The TNC is not connected in Host Mode."),
            ("ok" if mymail_set else "info",
             "MYMAIL is set - only needed so OTHER stations can reach the "
             "mailbox",
             "MYMAIL is not set. Local administration works anyway; remote "
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

        self.lbl_archive_hint = QLabel()
        self.lbl_archive_hint.setFont(QFont(FONT_UI, 8))
        self.lbl_archive_hint.setWordWrap(True)
        self.lbl_archive_hint.setStyleSheet(f"color: {_muted()};")
        lay.addWidget(self.lbl_archive_hint)

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
                             "Read every un-synced TNC message and store it "
                             "in the local archive")
        self.btn_sync.clicked.connect(self._on_sync_clicked)
        self.btn_restore = _btn("Restore to TNC",
                                "Write archive-only messages back into the "
                                "TNC, keeping sender, BBS and type")
        self.btn_restore.clicked.connect(self._on_restore_clicked)
        row.addWidget(self.btn_sync)
        row.addWidget(self.btn_restore)
        row.addWidget(_vsep())

        self.btn_new = _btn("New...", "Write a new message", _BTN_PRIMARY)
        self.btn_new.clicked.connect(lambda: self._compose(None))
        self.btn_reply = _btn("Reply", "Reply to the selected message")
        self.btn_reply.clicked.connect(lambda: self._compose(self._current_row()))
        self.btn_kill = _btn("Kill", "Delete the selected message", _BTN_DANGER)
        self.btn_kill.clicked.connect(self._on_kill_clicked)
        self.btn_header = _btn(
            "Header...", "EDIT not measured yet - see Backlog.md"
        )
        self.btn_header.setEnabled(False)
        self.btn_save = _btn("Save as...", "Save the message to a text file")
        self.btn_save.clicked.connect(self._on_save_clicked)
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
        row.addStretch()

        self.btn_end = _btn("End session", "Send B and return to Host Mode",
                            _BTN_END, 150)
        self.btn_end.setFont(QFont(FONT_UI, 9, QFont.Weight.Bold))
        self.btn_end.clicked.connect(self.session.leave)
        row.addWidget(self.btn_end)

        self.btn_close = _btn("Close", width=90)
        self.btn_close.clicked.connect(self.close)
        row.addWidget(self.btn_close)
        col.addLayout(row)

        self.lbl_footer = QLabel()
        self.lbl_footer.setFont(QFont(FONT_UI, 8))
        self.lbl_footer.setStyleSheet(f"color: {_muted()};")
        col.addWidget(self.lbl_footer)
        return col

    # -- state (signal-driven, P39.2/P39.3) ---------------------------

    def _on_state_changed(self, state: str) -> None:
        self._state = state
        self._apply_state()
        if state == "ACTIVE":
            self.session.list()
        elif state == "CLOSED" and self._closing_confirmed:
            # A window-close gesture (X/Esc/Close) was confirmed and
            # leave() has now actually finished - only NOW does the
            # QDialog itself close (P39.3.3). "End session" alone (no
            # close gesture) returns to the gate page and leaves the
            # window open, see btn_end above.
            if self._archive is not None:
                self._archive.close()
            super().accept()

    def _apply_state(self) -> None:
        state = self._state
        active = state == "ACTIVE"
        transitioning = state in ("OPENING", "CLOSING")
        failed = state == "FAILED"

        self.stack.setCurrentIndex(1 if state in ("ACTIVE", "CLOSING") else 0)
        self._set_row_visible(self._progress_row, transitioning)
        if state == "OPENING":
            self.lbl_progress.setText(
                "Leaving Host Mode ...  Confirming command prompt ...  "
                "Logging in to the mailbox (MDCHECK) ..."
            )
        elif state == "CLOSING":
            self.lbl_progress.setText(
                "Leaving the mailbox (B) ...  Re-entering Host Mode ...  "
                "Confirming Host Mode ..."
            )

        self.btn_retry.setVisible(failed)

        if active:
            self.banner.setText(
                "MailDrop session active   ·   packet operation is "
                "suspended   ·   incoming connects receive BUSY")
            self.banner.setStyleSheet(
                "background-color: #8a6a1e; color: #ffffff;"
                " border: 1px solid #6a4a0e; border-radius: 4px;")
        elif failed:
            self.banner.setText(
                "MailDrop session failed   ·   see the status line below")
            self.banner.setStyleSheet(
                "background-color: #6a3434; color: #ffffff;"
                " border: 1px solid #4a2424; border-radius: 4px;")
        elif transitioning:
            self.banner.setText("MailDrop session " + state.lower() + " ...")
            self.banner.setStyleSheet(
                "background-color: #24313d; color: #9fb4c4;"
                " border: 1px solid #2a3a4a; border-radius: 4px;")
        else:
            self.banner.setText(
                "Session closed   ·   normal packet operation")
            self.banner.setStyleSheet(
                "background-color: #24313d; color: #9fb4c4;"
                " border: 1px solid #2a3a4a; border-radius: 4px;")

        archive_note = (
            f"Archive: {self._md_config.archive_path}" if self._archive
            else "Local archive disabled - see Parameters -> MailDrop..."
        )
        self.lbl_footer.setText(
            f"{archive_note}     'End session' sends B and returns the "
            f"TNC to Host Mode." if active else archive_note
        )

        self.btn_end.setVisible(active)
        self.lbl_free.setText("")
        self.lbl_dot.setVisible(active)

        if state == "CLOSED" or failed:
            self._fill_checks()
            can_open, reason = self._can_open()
            self.btn_open.setEnabled(can_open and state == "CLOSED")
            self.lbl_gate_hint.setText("" if can_open else reason)
            self.lbl_gate_hint.setStyleSheet(
                f"color: {'#e8b23a' if not can_open else _muted()};")

        self._refresh_rows()

    # -- gate/close/retry actions --------------------------------------

    def _request_close(self) -> bool:
        """Common entry point for X, Esc (reject()) and the Close button
        (P39.3). Returns True when the dialog may close immediately."""
        if self._state in ("OPENING", "CLOSING"):
            return False
        if self._state != "ACTIVE":
            return True
        if self._closing_confirmed:
            return False   # leave() already in flight from a prior confirm
        reply = QMessageBox.question(
            self, "End MailDrop session",
            "The MailDrop session is still open. End it and return to "
            "normal packet operation?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
        self._closing_confirmed = True
        self.session.leave()
        return False

    def closeEvent(self, event) -> None:
        if self._request_close():
            event.accept()
        else:
            event.ignore()

    def reject(self) -> None:
        if self._request_close():
            super().reject()

    def _on_retry_clicked(self) -> None:
        """FAILED is a dead end for the OLD session object (CLAUDE.md:
        MailDropSession itself never re-answers open()/leave() from
        FAILED) - Retry rebuilds a fresh one and returns to the gate
        page, rather than pretending the same session can recover."""
        self._build_session()
        self._state = "CLOSED"
        self.lbl_status.setText("")
        self._apply_state()

    # -- prompt / listing / read / stored / killed / failed -------------

    def _on_prompt_info(self, info) -> None:
        self.lbl_free.setText(f"{info.free} bytes free")
        self.last_have_mail = info.have_mail

    def _on_listing(self, entries: list) -> None:
        self._tnc_entries = entries
        self._refresh_rows()

    def _on_message_read(self, entry, body: str) -> None:
        if self._pending_op == "sync":
            if self._archive is not None:
                self._archive.add(entry, body, device=self._device_release)
            self._advance_sync()
            return
        if self._pending_op == "preview":
            self._pending_op = None
            row = next(
                (r for r in self._rows if r.tnc_number == entry.number), None
            )
            if row is not None:
                row.body = body
                self._show_row(row)
            self._update_toolbar_enablement()
            return

    def _on_stored(self, number: int) -> None:
        if self._pending_op == "restore":
            self._advance_restore()
            return
        self.lbl_status.setText(f"Stored as #{number}.")
        self.lbl_status.setStyleSheet(f"color: {_muted()};")
        self.session.list()

    def _on_killed(self, number: int) -> None:
        self._pending_op = None
        self.session.list()

    def _on_failed(self, text: str) -> None:
        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet("color: #e05a5a;")
        if self._pending_op is not None:
            self._pending_op = None
            self._sync_queue.clear()
            self._restore_queue.clear()
            self._update_toolbar_enablement()

    # -- data / list rendering -----------------------------------------

    def _refresh_rows(self) -> None:
        archive_msgs = self._archive.all() if self._archive is not None else []
        by_key: dict[tuple, ArchivedMessage] = {}
        for am in archive_msgs:
            by_key.setdefault(
                _header_key(am.mtype, am.to_call, am.from_call, am.bbs,
                            am.subject, am.size),
                am,
            )
        matched_ids = set()
        rows: list[_Row] = []
        for e in self._tnc_entries:
            key = _header_key(e.mtype, e.to, e.frm, e.bbs, e.title, e.size)
            am = by_key.get(key)
            if am is not None:
                matched_ids.add(am.id)
                rows.append(_Row(
                    tnc_number=e.number, archive_id=am.id, mtype=e.mtype,
                    read=e.read, to=e.to, frm=e.frm, bbs=e.bbs,
                    stamp=e.stamp, size=e.size, subject=e.title,
                    body=am.body, where=WHERE_BOTH,
                ))
            else:
                rows.append(_Row(
                    tnc_number=e.number, archive_id=None, mtype=e.mtype,
                    read=e.read, to=e.to, frm=e.frm, bbs=e.bbs,
                    stamp=e.stamp, size=e.size, subject=e.title,
                    body=None, where=WHERE_TNC,
                ))
        for am in archive_msgs:
            if am.id in matched_ids:
                continue
            rows.append(_Row(
                tnc_number=None, archive_id=am.id, mtype=am.mtype,
                read=am.read_flag, to=am.to_call, frm=am.from_call,
                bbs=am.bbs, stamp=am.tnc_stamp, size=am.size,
                subject=am.subject, body=am.body, where=WHERE_ARCHIVE,
            ))
        self._rows = rows

        if self._archive is None or self._archive.count() == 0:
            self.lbl_archive_hint.setText(
                "Archive is empty (or disabled) - every message shows as "
                "'TNC only' until you sync."
            )
        else:
            self.lbl_archive_hint.setText("")

        self._fill_list()
        self._update_counts()
        self._update_toolbar_enablement()

    def _visible(self, r: _Row) -> bool:
        f = self.cb_filter.currentText()
        if f == "Unread":
            return not r.read
        if f == "Personal":
            return r.mtype == "P"
        if f == "Traffic":
            return r.mtype == "T"
        if f == "Bulletins":
            return r.mtype == "B"
        if f.startswith("At risk"):
            return r.where == WHERE_TNC
        if f == "Archive only":
            return r.where == WHERE_ARCHIVE
        return True

    def _fill_list(self) -> None:
        if not hasattr(self, "tree"):
            return
        self.tree.clear()
        for r in self._rows:
            if not self._visible(r):
                continue
            number_text = str(r.tnc_number) if r.tnc_number is not None else "-"
            read_text = "Y" if r.read else "N"
            it = QTreeWidgetItem([
                number_text, _TYPE_TEXT.get(r.mtype, r.mtype), read_text,
                _WHERE_TEXT[r.where], r.to, r.frm, r.bbs,
                r.stamp or "clock unset", str(r.size), r.subject])
            it.setData(0, Qt.ItemDataRole.UserRole, r)

            if r.where == WHERE_ARCHIVE:
                col = "#7d8c99"
            elif not r.read:
                col = "#ffffff"
            else:
                col = "#c8d4de"
            for c in range(len(self.COLS)):
                it.setForeground(c, QBrush(QColor(col)))
            it.setForeground(3, QBrush(QColor(_WHERE_COLOR[r.where])))
            it.setToolTip(3, _WHERE_TIP[r.where])
            if not r.read:
                for c in range(len(self.COLS)):
                    f = QFont(FONT_MONO, 9)
                    f.setBold(True)
                    it.setFont(c, f)
            self.tree.addTopLevelItem(it)

    def _update_counts(self) -> None:
        if self._state != "ACTIVE":
            arch = len(self._rows) if self._archive is not None else 0
            self.lbl_counts.setText(f"Archive {arch}" if self._archive else "")
            self.lbl_counts.setStyleSheet("color: #d0e4f4;")
            return
        tnc = sum(1 for r in self._rows if r.where != WHERE_ARCHIVE)
        arch = sum(1 for r in self._rows if r.where != WHERE_TNC)
        risk = sum(1 for r in self._rows if r.where == WHERE_TNC)
        self.lbl_counts.setText(
            f"TNC {tnc}   ·   Archive {arch}" +
            (f"   ·   {risk} at risk" if risk else ""))
        self.lbl_counts.setStyleSheet(
            "color: #e8b23a;" if risk else "color: #d0e4f4;")

    def _current_row(self) -> Optional[_Row]:
        if not hasattr(self, "tree"):
            return None
        it = self.tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def _update_toolbar_enablement(self) -> None:
        if not hasattr(self, "btn_sync"):
            return
        active = self._state == "ACTIVE"
        archive_on = self._archive is not None
        busy = self._pending_op is not None
        has_archive_only = any(r.where == WHERE_ARCHIVE for r in self._rows)

        self.btn_sync.setEnabled(active and archive_on and not busy)
        self.btn_sync.setToolTip(
            "Read every un-synced TNC message and store it in the local "
            "archive" if archive_on else
            "Enable the local archive in Parameters -> MailDrop... first."
        )
        self.btn_restore.setEnabled(
            active and archive_on and not busy and has_archive_only
        )
        if not archive_on:
            self.btn_restore.setToolTip(
                "Enable the local archive in Parameters -> MailDrop... first."
            )
        elif not has_archive_only:
            self.btn_restore.setToolTip("Nothing archive-only to restore.")
        else:
            self.btn_restore.setToolTip(
                "Write archive-only messages back into the TNC, keeping "
                "sender, BBS and type"
            )

        row = self._current_row()
        has_row = row is not None
        self.btn_new.setEnabled(active and not busy)
        self.btn_reply.setEnabled(active and not busy and has_row)
        self.btn_kill.setEnabled(active and not busy and has_row)
        self.btn_save.setEnabled(active and not busy and has_row
                                  and row.body is not None)
        self.tree.setEnabled(active and not busy)

    def _on_select(self, cur, _prev) -> None:
        row = cur.data(0, Qt.ItemDataRole.UserRole) if cur else None
        self._update_toolbar_enablement()
        if row is None:
            self.lbl_head.clear()
            self.reader.clear()
            return
        if row.body is not None:
            self._show_row(row)
        elif self._pending_op is None and row.tnc_number is not None:
            self.reader.setPlainText("Loading ...")
            self.lbl_head.clear()
            self._pending_op = "preview"
            self.session.read(row.tnc_number)

    def _show_row(self, r: _Row) -> None:
        bbs = f" @ {r.bbs}" if r.bbs else ""
        where = (f'<span style="color:{_WHERE_COLOR[r.where]};">'
                 f'{_WHERE_TEXT[r.where]}</span>')
        number_text = str(r.tnc_number) if r.tnc_number is not None else "-"
        self.lbl_head.setText(
            f'<b>{r.subject}</b><br>'
            f'<span style="color:{_muted()};">From</span> {r.frm}{bbs}'
            f'&nbsp;&nbsp;<span style="color:{_muted()};">To</span> {r.to}'
            f'&nbsp;&nbsp;<span style="color:{_muted()};">Date</span> '
            f'{r.stamp or "clock unset"}'
            f'&nbsp;&nbsp;<span style="color:{_muted()};">Msg</span> '
            f'{number_text}&nbsp;&nbsp;{_TYPE_TEXT.get(r.mtype, r.mtype)}'
            f'&nbsp;&nbsp;{where}')
        self.reader.setPlainText(r.body or "")
        self._update_toolbar_enablement()

    # -- compose / kill / save -----------------------------------------

    def _compose(self, reply_row: Optional[_Row]) -> None:
        dlg = MailComposeDialog(reply_row, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.session.send(**dlg.get_send_args())

    def _on_kill_clicked(self) -> None:
        row = self._current_row()
        if row is None:
            return
        where_text = {
            WHERE_BOTH: "from the TNC and from the local archive",
            WHERE_TNC: "from the TNC",
            WHERE_ARCHIVE: "from the local archive",
        }[row.where]
        reply = QMessageBox.question(
            self, "Kill message",
            f"Delete message '{row.subject}' {where_text}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if row.archive_id is not None and self._archive is not None:
            self._archive.delete(row.archive_id)
        if row.tnc_number is not None:
            self._pending_op = "kill"
            self.session.kill(row.tnc_number)
        else:
            self._refresh_rows()

    def _on_save_clicked(self) -> None:
        row = self._current_row()
        if row is None or row.body is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save message", f"{row.subject or 'message'}.txt",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(row.body)
        except OSError as exc:
            QMessageBox.warning(self, "Save message", f"Could not save: {exc}")

    # -- sync / restore --------------------------------------------------

    def _on_sync_clicked(self) -> None:
        if self._archive is None or self._pending_op is not None:
            return
        queue = [r.tnc_number for r in self._rows
                 if r.where == WHERE_TNC and r.tnc_number is not None]
        if not queue:
            QMessageBox.information(self, "Sync to archive",
                                    "Nothing new to sync.")
            return
        self._pending_op = "sync"
        self._sync_queue = queue
        self._update_toolbar_enablement()
        self._advance_sync()

    def _advance_sync(self) -> None:
        if not self._sync_queue:
            self._pending_op = None
            self._update_toolbar_enablement()
            self.session.list()
            return
        number = self._sync_queue.pop(0)
        self.lbl_status.setText(f"Syncing message #{number} to the archive...")
        self.lbl_status.setStyleSheet(f"color: {_muted()};")
        self.session.read(number)

    def _on_restore_clicked(self) -> None:
        if self._archive is None or self._pending_op is not None:
            return
        queue = [r for r in self._rows if r.where == WHERE_ARCHIVE]
        if not queue:
            return
        self._pending_op = "restore"
        self._restore_queue = queue
        self._update_toolbar_enablement()
        self._advance_restore()

    def _advance_restore(self) -> None:
        if not self._restore_queue:
            self._pending_op = None
            self._update_toolbar_enablement()
            self.session.list()
            return
        row = self._restore_queue.pop(0)
        self.lbl_status.setText(f"Restoring '{row.subject}' to the TNC...")
        self.lbl_status.setStyleSheet(f"color: {_muted()};")
        frm = "" if row.frm.strip().upper() == self._mycall else row.frm
        self.session.send(row.to, row.bbs, frm, row.mtype, row.subject,
                          row.body or "")
