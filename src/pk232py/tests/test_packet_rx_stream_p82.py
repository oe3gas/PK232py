# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  —  GPL v2
"""P82 - received channel data is a STREAM, not one finished line per frame.

T169 screenshot (device B, TinyBox help in ALL): every $3x frame got its own
line, an extra blank line and a 9-character indent, and the TinyBox's fixed
length packets broke words in the middle ("Download the b" / "rocast
dictionary", "K n K" / "ill message", "TS = Ty" / "pe (P private"). Measured on
the document content (toPlainText()).

The bytes are the OBSERVED ones, verbatim: "brocast" is the TinyBox's own word
(confirmed by the operator), not a typo to correct.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from pk232py.ui.screens.packet_screen import HFPacketScreen

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def screen():
    s = HFPacketScreen()
    s.resize(900, 500)
    s.show()
    _app.processEvents()
    yield s
    s.close()


def rx(screen, channel, data: bytes) -> None:
    screen.append_received_data(channel, data.decode("ascii"))


def all_text(screen) -> str:
    return screen._rx_doc_all.toPlainText()


def ch_text(screen, channel) -> str:
    return screen._rx_docs[channel].toPlainText()


class TestPacketBoundariesFromTheScreenshot:
    @pytest.mark.parametrize("first, second, joined", [
        (b"Download the b", b"rocast dictionary", "Download the brocast dictionary"),
        (b"K n K", b"ill message", "K n Kill message"),
        (b"TS = Ty", b"pe (P private", "TS = Type (P private"),
    ])
    def test_a_word_split_by_the_packet_boundary_stays_one_word(self, screen, first, second, joined):
        rx(screen, 1, first)
        rx(screen, 1, second)
        assert ch_text(screen, 1) == joined
        assert all_text(screen) == f"1│{joined}"

    def test_the_whole_help_text_in_fixed_length_packets(self, screen):
        text = ("Commands: Download the brocast dictionary\r"
                "K = Kill message\rTS = Type (P private)\r")
        for i in range(0, len(text), 14):                  # fixed length, mid-word
            rx(screen, 1, text[i:i + 14].encode("ascii"))
        lines = ch_text(screen, 1).split("\n")
        assert lines[:3] == ["Commands: Download the brocast dictionary",
                             "K = Kill message", "TS = Type (P private)"]
        assert not any(line.startswith(" ") for line in lines)     # no indent
        assert "" not in lines[:3]                                 # no extra blank line


class TestLineBreaks:
    def test_cr_lf_and_crlf_are_one_break_each(self, screen):
        rx(screen, 1, b"a\rb\nc\r\nd")
        assert ch_text(screen, 1) == "a\nb\nc\nd"

    def test_crlf_split_across_two_frames_is_one_break(self, screen):
        rx(screen, 1, b"first\r")
        rx(screen, 1, b"\nsecond")
        assert ch_text(screen, 1) == "first\nsecond"

    def test_a_blank_line_in_the_text_is_kept_but_none_is_added(self, screen):
        rx(screen, 1, b"a\r\rb\r")
        assert ch_text(screen, 1).rstrip("\n").split("\n") == ["a", "", "b"]

    def test_no_indent_for_a_multi_line_frame(self, screen):
        rx(screen, 1, b"one\rtwo\rthree")
        assert ch_text(screen, 1) == "one\ntwo\nthree"

    def test_prompt_without_cr_is_visible_at_once(self, screen):
        rx(screen, 1, b"TinyBox (A,B,H,J,K,L,R,S,V,?) > ")
        assert ch_text(screen, 1) == "TinyBox (A,B,H,J,K,L,R,S,V,?) > "
        assert all_text(screen) == "1│TinyBox (A,B,H,J,K,L,R,S,V,?) > "

    def test_the_continuation_goes_on_the_same_line(self, screen):
        rx(screen, 1, b"> ")
        rx(screen, 1, b"L\r")
        assert ch_text(screen, 1) == "> L\n"


class TestAllViewTags:
    def test_tag_and_timestamp_only_at_the_start_of_a_line(self, screen):
        screen.apply_display_settings(True, 5000)
        rx(screen, 1, b"ab")
        rx(screen, 1, b"cd\ref")
        lines = all_text(screen).split("\n")
        assert len(lines) == 2
        assert lines[0].count("│") == 1 and lines[0].endswith("1│abcd")
        assert lines[0].startswith("[") and lines[1].endswith("1│ef")

    def test_another_channel_ends_the_open_line_and_starts_its_own(self, screen):
        rx(screen, 1, b"abc")
        rx(screen, 2, b"xyz")
        rx(screen, 1, b"def")
        assert all_text(screen) == "1│abc\n2│xyz\n1│def"
        assert ch_text(screen, 1) == "abcdef"          # its own document is a clean stream
        assert ch_text(screen, 2) == "xyz"

    def test_the_same_channel_continues_after_its_own_break(self, screen):
        rx(screen, 1, b"abc\r")
        rx(screen, 2, b"xyz\r")
        rx(screen, 1, b"def")
        assert all_text(screen) == "1│abc\n2│xyz\n1│def"


class TestSystemLines:
    def test_a_link_message_ends_the_open_line_and_is_its_own_line(self, screen):
        rx(screen, 1, b"abc")
        screen.append_channel_data(1, "*** DISCONNECTED: OE3GAS-1 ***", color="#ffaa00")
        rx(screen, 1, b"def")
        assert ch_text(screen, 1).startswith("abc\n*** DISCONNECTED: OE3GAS-1 ***")
        assert ch_text(screen, 1).endswith("def")
        assert "abc\n*** DISCONNECTED" in ch_text(screen, 1)
        assert "\ndef" in ch_text(screen, 1)           # the data starts a NEW line
        assert "1│abc\n1│*** DISCONNECTED" in all_text(screen)

    def test_a_system_line_in_the_all_view_closes_another_channels_line(self, screen):
        rx(screen, 2, b"xyz")
        screen.append_channel_data(1, "*** CONNECTED to OE3GAS-1 ***", color="#ffaa00")
        assert all_text(screen).startswith("2│xyz\n1│*** CONNECTED")

    def test_monitor_lines_close_an_open_line(self, screen):
        rx(screen, 1, b"abc")
        screen.append_monitor_data("mon frame")
        assert all_text(screen).startswith("1│abc\nMON│mon frame")


class TestStatusLine:
    def test_rx_lines_counts_the_document_that_is_shown(self, screen):
        assert screen.lbl_sb_rxsize.text() == "RX: 0 lines"
        rx(screen, 1, b"a\rb\rc")
        assert screen.lbl_sb_rxsize.text() == "RX: 3 lines"         # ALL: the open line counts
        screen.channel_bar.set_current(2)
        rx(screen, 2, b"x\r")
        assert screen.lbl_sb_rxsize.text() == "RX: 4 lines"          # ALL view, 4 lines
        screen.set_view_all(False)
        _app.processEvents()
        assert screen.lbl_sb_rxsize.text() == "RX: 1 lines"          # channel 2 only

    def test_partner_follows_the_link_table_without_a_channel_switch(self):
        from pk232py.ui.main_window import MainWindow
        w = MainWindow()
        screen = w._opmode_screens["HF Packet"]
        screen.channel_bar.set_current(1)
        assert screen.lbl_sb_partner.text() == "Partner: —"
        w._link_table.on_host_link_message(1, "*** CONNECTED to OE3GAS-1")
        assert screen.lbl_sb_partner.text() == "Partner: OE3GAS-1"
        w._link_table.on_host_link_message(1, "*** DISCONNECTED: OE3GAS-1 ***")
        assert screen.lbl_sb_partner.text() == "Partner: —"

    def test_the_data_path_of_the_main_window_keeps_cr_and_lf(self):
        from pk232py.ui.main_window import MainWindow
        w = MainWindow()
        screen = w._opmode_screens["HF Packet"]
        w._opmode_stack.setCurrentWidget(screen)
        w._on_packet_data_received(1, b"Download the b")
        w._on_packet_data_received(1, b"rocast dictionary\r\nnext\r")
        assert screen._rx_docs[1].toPlainText() == "Download the brocast dictionary\nnext\n"
