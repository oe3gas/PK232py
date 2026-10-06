# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P78 A/B (Qt-free parts): the release fingerprint and the verbose was/now parser."""

from __future__ import annotations

import pytest

from pk232py.comm.devices import KNOWN_DEVICES, infer_release
from pk232py.comm.params_uploader import ParamsUploader
from pk232py.comm.verbose_parse import (
    HF_PACKET_FIELDS, VerboseSync, parse_was_now,
)
from pk232py.config import AppConfig


class TestInferRelease:
    # T180: device C answers EXPERT with ?What? / $07 too, so the answer alone is ambiguous; the
    # second question (MAILDROP, derived from the command matrix) decides between B and C.
    def test_what_alone_is_ambiguous_between_b_and_c(self):
        assert infer_release("EXPERT\r\n?What?\r\ncmd:") is None
        assert infer_release("?What?") is None

    def test_what_and_a_maildrop_value_means_the_mbx_generation(self):
        second = lambda name: "MAILDROP\r\nMAildrop  OFF\r\ncmd:"       # noqa: E731 (T179, device B)
        assert infer_release("EXPERT\r\n?What?\r\ncmd:", second=second) == ("01.AUG.91", "inferred")
        assert infer_release("?What?", second=second) == ("01.AUG.91", "inferred")

    def test_host_error_07_and_a_maildrop_value_means_the_mbx_generation(self):
        assert infer_release(b"EX\x07") is None
        assert infer_release(b"EX\x07", second=lambda n: b"MVN") == ("01.AUG.91", "inferred")
        assert infer_release(b"\x07", second=lambda n: b"MVN") == ("01.AUG.91", "inferred")

    def test_a_value_means_the_pactor_generation(self):
        assert infer_release(b"EXN") == ("13.SEP.95", "inferred")
        assert infer_release(b"EXY") == ("13.SEP.95", "inferred")
        assert infer_release("EXPert    OFF\r\ncmd:") == ("13.SEP.95", "inferred")
        assert infer_release("EXPert    ON \r\ncmd:") == ("13.SEP.95", "inferred")

    def test_anything_else_is_none(self):
        assert infer_release(None) is None
        assert infer_release("") is None
        assert infer_release("cmd:") is None
        assert infer_release(b"") is None
        assert infer_release(b"EX\x10") is None         # another error code
        assert infer_release(b"ZZ") is None

    def test_device_c_answers_expert_like_b_only_that_is_measured(self):
        c = [d for d in KNOWN_DEVICES if d.label == "C"][0]
        assert c.release == "30.DEC.88" and c.expert == "absent"     # T180; the rest stays unmeasured
        assert c.unknown_verbose is None

    def test_a_second_device_of_a_generation_makes_it_ambiguous(self, monkeypatch):
        from pk232py.comm import devices
        twin = devices.KnownDevice("B2", "MBX", "02.FEB.92", "absent")
        monkeypatch.setattr(devices, "KNOWN_DEVICES", devices.KNOWN_DEVICES + (twin,))
        assert devices.infer_release("?What?") is None
        assert devices.infer_release(b"EXN") == ("13.SEP.95", "inferred")


# Real lines from the hw_logs (T151 / init upload).
MONITOR_LINES = ["MOnitor    was 4 (UA DM C D I UI)", "MOnitor    now 3 (UA DM C D I UI)"]


class TestParseWasNow:
    def test_monitor(self):
        assert parse_was_now(MONITOR_LINES) == ("MONITOR", "4", "3")

    def test_the_value_keeps_only_what_precedes_the_explanation(self):
        lines = ["TXdelay   was 30 (300 msec.)", "TXdelay   now 31 (310 msec.)"]
        assert parse_was_now(lines) == ("TXDELAY", "30", "31")

    def test_maxframe_is_matched_case_insensitively(self):
        assert parse_was_now(["MAXframe was 4", "MAXframe now 5"]) == ("MAXFRAME", "4", "5")

    def test_ubit_with_index_0(self):
        assert parse_was_now(["UBit   0  was ON", "UBit   0  now OFF"]) == ("UBIT", "ON", "OFF")

    def test_other_ubit_indexes_are_not_ours(self):
        assert parse_was_now(["UBit   3  was ON", "UBit   3  now OFF"]) is None

    def test_text_values_keep_their_words(self):
        lines = ["Unproto   was APZ232", "Unproto   now APZ232 via WIDE1-1, WIDE2-1"]
        assert parse_was_now(lines) == ("UNPROTO", "APZ232", "APZ232 via WIDE1-1, WIDE2-1")

    def test_daystamp_keeps_its_verbose_name(self):
        assert parse_was_now(["DAYStamp was OFF", "DAYStamp now ON"]) == ("DAYSTAMP", "OFF", "ON")

    def test_no_pair_no_result(self):
        assert parse_was_now(["MOnitor    was 4"]) is None
        assert parse_was_now(["cmd:", "MONITOR 3"]) is None
        assert parse_was_now([]) is None

    def test_was_and_now_of_different_parameters_do_not_pair(self):
        assert parse_was_now(["MOnitor was 4", "PACLen now 3"]) is None


class TestVerboseSync:
    def test_a_pair_split_over_chunks_is_found_once(self):
        sync = VerboseSync()
        assert sync.feed("MOnitor    was 4 (UA DM C D I UI)\r\nMOni") == []
        got = sync.feed("tor    now 3 (UA DM C D I UI)\r\ncmd:")
        assert got == [("MONITOR", "4", "3")]

    def test_two_changes_in_one_chunk(self):
        sync = VerboseSync()
        text = "MAXframe was 4\r\nMAXframe now 5\r\nPACLen was 128\r\nPACLen now 64\r\ncmd:"
        assert sync.feed(text) == [("MAXFRAME", "4", "5"), ("PACLEN", "128", "64")]

    def test_echo_and_prompt_are_ignored(self):
        assert VerboseSync().feed("MONITOR 3\r\ncmd:") == []


class TestFieldTable:
    def test_every_mapped_name_is_a_name_the_uploader_sends(self):
        cfg = AppConfig()
        cfg.hf_packet.mycall = "OE3GAS"        # MYCALL/BTEXT/CTEXT/UNPROTO are
        cfg.hf_packet.btext = "beacon"         # only sent when they are set
        cfg.hf_packet.ctext = "hello"
        cfg.hf_packet.unproto = "CQ"
        sent = {cmd.decode().split()[0] for cmd in
                ParamsUploader(None, cfg)._build_commands(has_pactor=True)}
        missing = [n for n in HF_PACKET_FIELDS if n not in sent]
        assert not missing, missing

    def test_every_mapped_attribute_exists_in_the_config(self):
        cfg = AppConfig().hf_packet
        for name, (attr, _kind) in HF_PACKET_FIELDS.items():
            if isinstance(attr, dict):                # band values
                for a in attr.values():
                    assert hasattr(cfg, a), (name, a)
            else:
                assert hasattr(cfg, attr), (name, attr)
