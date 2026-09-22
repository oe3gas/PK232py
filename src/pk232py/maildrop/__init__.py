# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop — personal mailbox controller and message store."""

from .maildrop      import MailDropController
from .message_store import MessageStore, MailMessage

__all__ = ["MailDropController", "MessageStore", "MailMessage"]