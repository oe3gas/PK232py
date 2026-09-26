# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop — verbose-mode mailbox session, protocol, and local archive.

`MailDropController` (Host Mode mnemonic upload, geraten/unverified) is
gone as of P27 — MDCHECK has no Host Mode mnemonic at all
(`mdcheck_scan`, docs/P26_MDCHECK_Mnemonic_Spec.md), so mailbox handling
lives entirely in `protocol`/`session` on the verbose-mode link instead.

`message_store.py` (MessageStore/MailMessage) is gone as of P38 — its
schema did not cover what a real archive needs (no TNC message number,
no @BBS, no P/T/B type, local instead of TNC timestamp, see P27.3) and
was replaced outright by `archive.MailDropArchive`.
"""

from .protocol       import MailDropEntry, PromptInfo
from .session        import MailDropSession, SerialManagerChannel
from .archive        import (
    ArchivedMessage, MailDropArchive, RESTORE_SCOPES, filter_restore_scope,
    open_archive,
)

__all__ = [
    "MailDropEntry", "PromptInfo",
    "MailDropSession", "SerialManagerChannel",
    "ArchivedMessage", "MailDropArchive", "open_archive",
    "RESTORE_SCOPES", "filter_restore_scope",
]