# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""MailDrop Mode — activates PK-232MBX personal mailbox.

The MailDrop is not a separate RF mode but a TNC feature that enables
the built-in personal mailbox.  Selecting this mode:
  1. Activates HF Packet (the underlying transport)
  2. Enables MAILDROP ON
  3. Optionally enables TMAIL (PACTOR MailDrop)
"""

from __future__ import annotations
from .base_mode import BaseMode
from .packet_hf import HFPacketMode


class MailDropMode(HFPacketMode):
    """MailDrop operating mode — personal mailbox via HF Packet.

    Builds on HFPacketMode: same b'PA' host command to enter packet,
    but additionally sends MAILDROP ON after activation.
    """

    name         = "MailDrop"
    host_command = b'PA'          # underlying transport is HF Packet
    verbose_command = b"PACKET\r\n"

    def __init__(
        self,
        tmail: bool = False,      # enable PACTOR MailDrop as well
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.tmail = tmail