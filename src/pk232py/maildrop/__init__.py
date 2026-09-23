# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop — verbose-mode mailbox session, protocol, and message store.

`MailDropController` (Host Mode mnemonic upload, geraten/unverified) is
gone as of P27 — MDCHECK has no Host Mode mnemonic at all
(`mdcheck_scan`, docs/P26_MDCHECK_Mnemonic_Spec.md), so mailbox handling
lives entirely in `protocol`/`session` on the verbose-mode link instead.
"""

from .protocol       import MailDropEntry, PromptInfo
from .session        import MailDropSession, SerialManagerChannel
from .message_store  import MessageStore, MailMessage

__all__ = [
    "MailDropEntry", "PromptInfo",
    "MailDropSession", "SerialManagerChannel",
    "MessageStore", "MailMessage",
]