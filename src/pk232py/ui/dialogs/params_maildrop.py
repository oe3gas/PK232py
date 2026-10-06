# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop Parameters dialog — matches PCPackRatt 'MailDrop Parameters'."""

from __future__ import annotations
import logging
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from pk232py.ui.dialogs.param_order import add_form_rows, sorted_flags, split_columns

logger = logging.getLogger(__name__)


class MailDropParamsDialog(QDialog):
    """MailDrop Parameters dialog matching PCPackRatt layout."""

    DEFAULTS = dict(
        homebbs="", mymail="", lastmsg=0,
        mdprompt="Subject:", tmprompt="GA SUBJ",
        mtext="Welcome To My Personal Mail Box.",
        # flags
        third_party=False, kilonfwd=True,
        maildrop=False, mdmon=False, mmsg=True, tmail=False,
        # Local archive (PC side, P38) - matches MailDropConfig's own
        # defaults in config.py.
        archive_enabled=False,
        archive_path="~/.pk232py/maildrop_archive.db",
        archive_sync="manual",
        archive_restore="never",
        archive_restore_scope="unread",
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MailDrop Parameters")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build_ui()
        self.set_values(**self.DEFAULTS)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Text parameters ───────────────────────────────────────────
        params_group = QGroupBox("Parameters")
        form = QFormLayout(params_group)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # P87: placed by add_form_rows() (alphabetical, param_order.py)
        self._le_homebbs  = QLineEdit(); self._le_homebbs.setMaximumWidth(120)
        self._le_mymail   = QLineEdit(); self._le_mymail.setMaximumWidth(120)
        self._sb_lastmsg  = QSpinBox(); self._sb_lastmsg.setRange(0, 9999)
        self._le_mdprompt = QLineEdit()
        self._le_tmprompt = QLineEdit()
        add_form_rows(form, [
            ("HOMEBBS:", self._le_homebbs), ("MYMAIL:", self._le_mymail),
            ("LASTMSG:", self._sb_lastmsg), ("MDPROMPT:", self._le_mdprompt),
            ("TMPROMPT:", self._le_tmprompt),
        ])

        root.addWidget(params_group)

        # ── Welcome text ──────────────────────────────────────────────
        mtext_group = QGroupBox("MTEXT (Welcome message)")
        mtext_layout = QVBoxLayout(mtext_group)
        self._te_mtext = QTextEdit()
        self._te_mtext.setFixedHeight(80)
        self._te_mtext.setPlaceholderText("Welcome message shown to connecting stations")
        mtext_layout.addWidget(self._te_mtext)
        root.addWidget(mtext_group)

        # ── Flags ─────────────────────────────────────────────────────
        flags_group = QGroupBox("Flags")
        fl = QVBoxLayout(flags_group)
        row = QHBoxLayout()

        # P87: the six switches sorted (param_order.py), two columns top to bottom
        self._chk_third_party = QCheckBox("3RDPARTY")
        self._chk_kilonfwd    = QCheckBox("KILONFWD")
        self._chk_maildrop    = QCheckBox("MAILDROP")
        self._chk_mdmon  = QCheckBox("MDMON")
        self._chk_mmsg   = QCheckBox("MMSG")
        self._chk_tmail  = QCheckBox("TMAIL")
        col1 = QVBoxLayout()
        col2 = QVBoxLayout()
        for layout, boxes in zip((col1, col2), split_columns(sorted_flags([
                self._chk_third_party, self._chk_kilonfwd, self._chk_maildrop,
                self._chk_mdmon, self._chk_mmsg, self._chk_tmail]), 2)):
            for box in boxes:
                layout.addWidget(box)

        row.addLayout(col1)
        row.addLayout(col2)
        fl.addLayout(row)
        root.addWidget(flags_group)

        # ── Local archive (PC side, P38) ────────────────────────────────
        # This section is PK232PY's own bookkeeping, never sent to the TNC
        # (see MailDropConfig.archive_* in config.py and UPLOAD_EXEMPT in
        # test_param_dialogs_roundtrip.py). archive_sync/archive_restore
        # ARE wired up as of P59: 'on_session_end' collects TNC-only
        # messages when the MailDrop session ends; 'ask'/'auto' restore
        # from the archive when MainWindow detects the TNC came up at
        # factory defaults (a one-shot power-on event derived from the
        # boot banner, consumed exactly once per power cycle - P60)
        # and a MailDrop session is possible (docs/P38_MailDrop_
        # Archive_Spec.md P38.3, docs/P59_MailDrop_Archive_Auto_Spec.md,
        # docs/P60_Archive_Restore_Oneshot_Fix_Spec.md).
        archive_group = QGroupBox("Local archive (PC side)")
        archive_layout = QVBoxLayout(archive_group)

        intro = QLabel(
            "Keeps a local copy of MailDrop messages on this PC, since "
            "the TNC itself loses its mailbox on every power-off. These "
            "settings are never sent to the TNC."
        )
        intro.setWordWrap(True)
        archive_layout.addWidget(intro)

        self._chk_archive_enabled = QCheckBox("Enable local archive")
        archive_layout.addWidget(self._chk_archive_enabled)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Path:"))
        self._le_archive_path = QLineEdit()
        path_row.addWidget(self._le_archive_path)
        self._btn_archive_path = QPushButton("Browse...")
        self._btn_archive_path.clicked.connect(self._on_browse_archive_path)
        path_row.addWidget(self._btn_archive_path)
        archive_layout.addLayout(path_row)

        sync_row = QHBoxLayout()
        sync_row.addWidget(QLabel("Sync:"))
        self._cb_archive_sync = QComboBox()
        self._cb_archive_sync.addItem("manual (only on demand)", "manual")
        self._cb_archive_sync.addItem(
            "on_session_end (collect automatically when leaving the session)",
            "on_session_end",
        )
        sync_row.addWidget(self._cb_archive_sync)
        archive_layout.addLayout(sync_row)

        restore_row = QHBoxLayout()
        restore_row.addWidget(QLabel("Restore:"))
        self._cb_archive_restore = QComboBox()
        self._cb_archive_restore.addItem("never", "never")
        self._cb_archive_restore.addItem(
            "ask (when the TNC comes up at factory defaults)", "ask",
        )
        self._cb_archive_restore.addItem("auto", "auto")
        self._cb_archive_restore.currentIndexChanged.connect(
            self._update_archive_auto_warning
        )
        restore_row.addWidget(self._cb_archive_restore)
        archive_layout.addLayout(restore_row)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Restore scope:"))
        self._cb_archive_restore_scope = QComboBox()
        self._cb_archive_restore_scope.addItem("unread", "unread")
        self._cb_archive_restore_scope.addItem("all", "all")
        self._cb_archive_restore_scope.addItem("none", "none")
        scope_row.addWidget(self._cb_archive_restore_scope)
        archive_layout.addLayout(scope_row)

        restore_cost = QLabel(
            "Restoring messages takes about 7 seconds each and suspends "
            "packet operation for the whole session - other stations "
            "receive BUSY."
        )
        restore_cost.setWordWrap(True)
        archive_layout.addWidget(restore_cost)

        self._lbl_archive_auto_warn = QLabel(
            '"auto" also makes the application take longer to start.'
        )
        self._lbl_archive_auto_warn.setWordWrap(True)
        archive_layout.addWidget(self._lbl_archive_auto_warn)

        effect_note = QLabel(
            "'on_session_end' collects new messages when you end a "
            "MailDrop session. 'ask'/'auto' restore from the archive "
            "when the TNC comes up at factory defaults (detected from "
            "its power-on banner) and a MailDrop session is possible."
        )
        effect_note.setWordWrap(True)
        archive_layout.addWidget(effect_note)

        root.addWidget(archive_group)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _on_browse_archive_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Local MailDrop archive file",
            self._le_archive_path.text(),
            "SQLite database (*.db);;All files (*)",
        )
        if path:
            self._le_archive_path.setText(path)

    def _update_archive_auto_warning(self) -> None:
        self._lbl_archive_auto_warn.setVisible(
            self._cb_archive_restore.currentData() == "auto"
        )

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def set_locked(self, locked: bool, reason: str = "") -> None:
        """Disable (never hide) every parameter field, with *reason* as
        the tooltip (P37 Teil D.3) - e.g. once SerialManager.detect_
        maildrop() has confirmed this firmware has no MailDrop option at
        all (docs/DEVICES.md Device C). Locking rather than hiding keeps
        the dialog layout stable and lets the operator still see what
        MailDrop parameters exist. OK/Cancel are left alone - saving
        locked-but-unchanged values is harmless, and Cancel always works.
        """
        widgets = [
            self._le_homebbs, self._le_mymail, self._sb_lastmsg,
            self._le_mdprompt, self._le_tmprompt, self._te_mtext,
            self._chk_third_party, self._chk_kilonfwd, self._chk_maildrop,
            self._chk_mdmon, self._chk_mmsg, self._chk_tmail,
        ]
        for w in widgets:
            w.setEnabled(not locked)
            w.setToolTip(reason if locked else "")

    def set_values(self, **kw) -> None:
        if "homebbs"     in kw: self._le_homebbs.setText(str(kw["homebbs"]).upper())
        if "mymail"      in kw: self._le_mymail.setText(str(kw["mymail"]).upper())
        if "lastmsg"     in kw: self._sb_lastmsg.setValue(int(kw["lastmsg"]))
        if "mdprompt"    in kw: self._le_mdprompt.setText(str(kw["mdprompt"]))
        if "tmprompt"    in kw: self._le_tmprompt.setText(str(kw["tmprompt"]))
        if "mtext"       in kw: self._te_mtext.setPlainText(str(kw["mtext"]))
        for attr, key in [
            ("_chk_third_party","third_party"),("_chk_kilonfwd","kilonfwd"),
            ("_chk_maildrop","maildrop"),("_chk_mdmon","mdmon"),
            ("_chk_mmsg","mmsg"),("_chk_tmail","tmail"),
        ]:
            if key in kw: getattr(self, attr).setChecked(bool(kw[key]))
        if "archive_enabled" in kw:
            self._chk_archive_enabled.setChecked(bool(kw["archive_enabled"]))
        if "archive_path" in kw:
            self._le_archive_path.setText(str(kw["archive_path"]))
        if "archive_sync" in kw:
            self._set_combo_data(self._cb_archive_sync, kw["archive_sync"])
        if "archive_restore" in kw:
            self._set_combo_data(self._cb_archive_restore, kw["archive_restore"])
        if "archive_restore_scope" in kw:
            self._set_combo_data(
                self._cb_archive_restore_scope, kw["archive_restore_scope"]
            )
        self._update_archive_auto_warning()

    def get_values(self) -> dict:
        return dict(
            homebbs     = self._le_homebbs.text().upper().strip(),
            mymail      = self._le_mymail.text().upper().strip(),
            lastmsg     = self._sb_lastmsg.value(),
            mdprompt    = self._le_mdprompt.text(),
            tmprompt    = self._le_tmprompt.text(),
            mtext       = self._te_mtext.toPlainText(),
            third_party = self._chk_third_party.isChecked(),
            kilonfwd    = self._chk_kilonfwd.isChecked(),
            maildrop    = self._chk_maildrop.isChecked(),
            mdmon       = self._chk_mdmon.isChecked(),
            mmsg        = self._chk_mmsg.isChecked(),
            tmail       = self._chk_tmail.isChecked(),
            archive_enabled       = self._chk_archive_enabled.isChecked(),
            archive_path          = self._le_archive_path.text().strip(),
            archive_sync          = self._cb_archive_sync.currentData(),
            archive_restore       = self._cb_archive_restore.currentData(),
            archive_restore_scope = self._cb_archive_restore_scope.currentData(),
        )