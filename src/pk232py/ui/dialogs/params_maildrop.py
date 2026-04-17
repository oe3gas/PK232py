# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop Parameters dialog — matches PCPackRatt 'MailDrop Parameters'."""

from __future__ import annotations
import logging
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

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

        self._le_homebbs  = QLineEdit(); self._le_homebbs.setMaximumWidth(120)
        form.addRow("HOMEBBS:",  self._le_homebbs)

        self._le_mymail   = QLineEdit(); self._le_mymail.setMaximumWidth(120)
        form.addRow("MYMAIL:",   self._le_mymail)

        self._sb_lastmsg  = QSpinBox(); self._sb_lastmsg.setRange(0, 9999)
        form.addRow("LASTMSG:",  self._sb_lastmsg)

        self._le_mdprompt = QLineEdit()
        form.addRow("MDPROMPT:", self._le_mdprompt)

        self._le_tmprompt = QLineEdit()
        form.addRow("TMPROMPT:", self._le_tmprompt)

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

        col1 = QVBoxLayout()
        self._chk_third_party = QCheckBox("3RDPARTY")
        self._chk_kilonfwd    = QCheckBox("KILONFWD")
        self._chk_maildrop    = QCheckBox("MAILDROP")
        for w in [self._chk_third_party, self._chk_kilonfwd, self._chk_maildrop]:
            col1.addWidget(w)

        col2 = QVBoxLayout()
        self._chk_mdmon  = QCheckBox("MDMON")
        self._chk_mmsg   = QCheckBox("MMSG")
        self._chk_tmail  = QCheckBox("TMAIL")
        for w in [self._chk_mdmon, self._chk_mmsg, self._chk_tmail]:
            col2.addWidget(w)

        row.addLayout(col1)
        row.addLayout(col2)
        fl.addLayout(row)
        root.addWidget(flags_group)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

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
        )