# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""T180 (device C, 06.10.2026, hw_logs/20261006_fw_scan_C*.log) - two findings.

1. The banner of device C prints ``Release 30.DEC.88``, not the transcription ``30.12.1988``
   (the same as for device A before: 11.09.1995 -> 13.SEP.95). Every release key of the
   project is the banner's own text, DD.MMM.YY.
2. Device C answers EXPERT with ``?What?`` like device B, so that answer alone cannot tell the
   two apart (P78 would have taken C for 01.AUG.91). The second question is derived from the
   command matrix: a command that is known on both candidates and differs - MAILDROP exists on
   01.AUG.91 and not on 30.DEC.88.
"""

from __future__ import annotations

import re

import pytest

from pk232py.comm import command_matrix as cm
from pk232py.comm import devices
from pk232py.comm.devices import KNOWN_DEVICES, infer_release
from pk232py.comm.mnemonic_registry import RELEASES as REGISTRY_RELEASES
from pk232py.comm.serial_manager import SerialManager, _parse_release

B, A, C = "01.AUG.91", "13.SEP.95", "30.DEC.88"
BANNER_FORMAT = re.compile(
    r"^\d{2}\.(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\.\d{2}$")

# Real lines (hw_logs/20261006_fw_scan_C.log, 20261006_fw_scan_B_run3.log), copied literally.
C_BANNER = (b"\x00\r\n\r\n\r\nPK-232 is using default values.\r\n  \r\n\r\n\r\n\x11AEA PK-232 Data "
            b"Controller\r\nCopyright (C) 1986, 1987, 1988 by\r\nAdvanced Electronic Applications, "
            b"Inc.\r\nRelease 30.DEC.88\r\nChecksum $80\r\ncmd:")
EXPERT_WHAT = "EXPERT\r\n?What?\r\ncmd:"                    # device B and device C
MAILDROP_B = "MAILDROP\r\nMAildrop  OFF\r\ncmd:"
MAILDROP_C = "MAILDROP\r\n?What?\r\ncmd:"


class TestReleaseKeysAreTheBannerFormat:

    def test_every_matrix_release_is_DD_MMM_YY(self):
        assert all(BANNER_FORMAT.match(r) for r in cm.RELEASES), cm.RELEASES

    def test_every_device_release_is_DD_MMM_YY(self):
        assert all(BANNER_FORMAT.match(d.release) for d in KNOWN_DEVICES)

    def test_the_registry_columns_are_DD_MMM_YY(self):
        assert all(BANNER_FORMAT.match(r) for r in REGISTRY_RELEASES), REGISTRY_RELEASES

    def test_the_matrix_file_columns_are_DD_MMM_YY(self):
        header = cm.DATA_FILE.read_text(encoding="utf-8").splitlines()[0].split(",")
        keys = [c.split("_", 1)[1] for c in header if c.startswith(("fw_", "ev_"))]
        assert keys and all(BANNER_FORMAT.match(k) for k in keys), keys

    def test_the_three_keys_are_the_ones_the_banners_print(self):
        assert set(cm.RELEASES) == {B, A, C}
        assert {d.release for d in KNOWN_DEVICES} == {B, A, C}

    def test_the_scanner_selftest_uses_banner_keys(self):
        import sys
        from pathlib import Path
        tools = Path(__file__).resolve().parents[3] / "tools"
        sys.path.insert(0, str(tools))
        import pk232_fw_scan
        assert all(BANNER_FORMAT.match(r) for r in pk232_fw_scan._SELFTEST_RELEASE.values())


class TestDeviceCByItsBanner:

    def test_the_app_reads_the_banner_release_verbatim(self):
        assert _parse_release(C_BANNER) == C

    def test_the_release_of_the_banner_is_a_known_device(self):
        assert [d.label for d in KNOWN_DEVICES if d.release == _parse_release(C_BANNER)] == ["C"]

    def test_what_follows_from_the_release(self):
        assert devices.has_pactor(C) is False             # BASE generation
        assert devices.unknown_commands(C) is None        # unmeasured: send everything


class TestSecondQuestionFromTheMatrix:

    def test_the_discriminator_is_derived_from_the_matrix(self):
        assert devices.discriminating_command([B, C]) == "MAILDROP"

    def test_a_different_matrix_gives_a_different_question(self, monkeypatch):
        # nothing about MAILDROP is coded in devices.py: with a matrix in which MAILDROP does not
        # differ, another command that does is chosen
        entries = cm.all_entries()
        import dataclasses
        e = entries["MAILDROP"]
        entries["MAILDROP"] = dataclasses.replace(e, fw={**e.fw, C: "yes"}, ev={**e.ev, C: "test"})
        m = entries["MBELL"]
        entries["MBELL"] = dataclasses.replace(m, fw={**m.fw, B: "yes", C: "no"}, ev={**m.ev, B: "t", C: "t"})
        monkeypatch.setattr(cm, "all_entries", lambda: entries)
        assert devices.discriminating_command([B, C]) == "MBELL"

    def test_no_command_that_is_unknown_on_a_candidate_is_a_question(self):
        assert devices.discriminating_command([B, B]) is None       # nothing differs

    def test_expert_what_alone_is_ambiguous_now(self):
        assert infer_release(EXPERT_WHAT) is None
        assert infer_release(b"EX\x07") is None
        assert devices.candidate_releases(EXPERT_WHAT) == [B, C]

    def test_maildrop_answers_decide_between_b_and_c(self):
        asked = []

        def second(name):
            asked.append(name)
            return MAILDROP_C
        assert infer_release(EXPERT_WHAT, second=second) == (C, "inferred")
        assert asked == ["MAILDROP"]
        assert infer_release(EXPERT_WHAT, second=lambda n: MAILDROP_B) == (B, "inferred")

    def test_an_unusable_second_answer_is_none(self):
        for answer in ("", None, "cmd:", "MAILDROP\r\n", "garbage"):
            assert infer_release(EXPERT_WHAT, second=lambda n, a=answer: a) is None

    def test_a_value_for_expert_needs_no_second_question(self):
        def never(name):
            raise AssertionError(f"asked {name} although EXPERT answered a value")
        assert infer_release("EXPert    OFF\r\ncmd:", second=never) == (A, "inferred")
        assert infer_release(b"EXN", second=never) == (A, "inferred")

    def test_host_mode_answers(self):
        # Host Mode: EX -> $07 on B and C; MAILDROP is MV (matrix host column)
        assert cm.host("MAILDROP") == "MV"
        assert infer_release(b"EX\x07", second=lambda n: b"MV\x07") == (C, "inferred")
        assert infer_release(b"EX\x07", second=lambda n: b"MVN") == (B, "inferred")
        assert infer_release(b"EX\x07", second=lambda n: b"MVY") == (B, "inferred")
        assert infer_release(b"EX\x07", second=lambda n: None) is None

    def test_the_expert_column_of_the_devices_agrees_with_the_matrix_where_measured(self):
        for d in KNOWN_DEVICES:
            cell = cm.exists("EXPERT", d.release)
            if cell == "?":
                continue
            assert (d.expert == "present") == (cell in ("yes", "expert")), d.label


class TestProbeReleaseVerbose:
    """SerialManager.probe_release_verbose(): the verbose side asks MAILDROP only when needed."""

    @staticmethod
    def _manager(monkeypatch, answers):
        sm = SerialManager()
        sent = []
        monkeypatch.setattr(SerialManager, "is_connected", property(lambda s: True))

        def fake(data, timeout=5.0):
            sent.append(data)
            return True, answers[data].encode("ascii")

        monkeypatch.setattr(sm, "_write_verbose_wait_text", fake)
        return sm, sent

    def test_device_c_is_recognised_without_a_banner(self, monkeypatch):
        sm, sent = self._manager(monkeypatch, {b"EXPERT\r": EXPERT_WHAT, b"MAILDROP\r": MAILDROP_C})
        sm.probe_release_verbose()
        assert (sm.tnc_release, sm.tnc_release_source) == (C, "inferred")
        assert sent == [b"EXPERT\r", b"MAILDROP\r"]

    def test_device_b_is_still_recognised(self, monkeypatch):
        sm, sent = self._manager(monkeypatch, {b"EXPERT\r": EXPERT_WHAT, b"MAILDROP\r": MAILDROP_B})
        sm.probe_release_verbose()
        assert sm.tnc_release == B and sent == [b"EXPERT\r", b"MAILDROP\r"]

    def test_device_a_needs_only_the_expert_question(self, monkeypatch):
        sm, sent = self._manager(monkeypatch, {b"EXPERT\r": "EXPERT\r\nEXPert    OFF\r\ncmd:"})
        sm.probe_release_verbose()
        assert sm.tnc_release == A and sent == [b"EXPERT\r"]


class TestHostModeRelease:
    """SerialParamTransport.release(): the second question uses the matrix's Host Mode mnemonic."""

    @staticmethod
    def _transport(answers):
        from pk232py.comm.param_applier import SerialParamTransport

        class Sm:
            tnc_release = None
            release_probe_attempted = False

            def set_inferred_release(self, release, source="inferred"):
                self.tnc_release = release

        asked = []
        t = SerialParamTransport(Sm(), lambda: False, lambda: False)
        t.mode = lambda: "host"
        t.host_exchange = lambda mnemonic, args: (asked.append(mnemonic) or answers.get(mnemonic))
        return t, asked

    def test_device_c_in_host_mode(self):
        t, asked = self._transport({b"EX": b"EX\x07", b"MV": b"MV\x07"})
        assert t.release() == C and asked == [b"EX", b"MV"]

    def test_device_b_in_host_mode(self):
        t, asked = self._transport({b"EX": b"EX\x07", b"MV": b"MVN"})
        assert t.release() == B and asked == [b"EX", b"MV"]

    def test_device_a_in_host_mode_needs_only_ex(self):
        t, asked = self._transport({b"EX": b"EXN"})
        assert t.release() == A and asked == [b"EX"]

    def test_no_answer_to_the_second_question_stays_unknown(self):
        t, _asked = self._transport({b"EX": b"EX\x07"})
        assert t.release() is None
