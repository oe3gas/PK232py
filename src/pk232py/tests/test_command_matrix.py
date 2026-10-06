# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P88 - the command matrix: schema, reader and the rules of the data file."""

from __future__ import annotations

import pytest

from pk232py.comm import command_matrix as cm

HEADER = ",".join(cm.COLUMNS)


def _row(name="ILFPACK", abbrev="IL", host="IL", kind="param", a="yes", b="yes", c="?",
         ev_a="T175 log", ev_b="T155", ev_c="", note="", fx_a="", fx_b="", fx_c=""):
    cells = [name, abbrev, host, kind, "ON", "Ignores line feeds", "timewave",
             b, a, c, ev_b, ev_a, ev_c, fx_b, fx_a, fx_c, note]
    return ",".join(cells)


def _csv(*rows):
    return "\n".join([HEADER, *rows]) + "\n"


class TestParse:

    def test_a_valid_file(self):
        entries = cm.parse(_csv(_row()))
        e = entries["ILFPACK"]
        assert e.fw == {"01.AUG.91": "yes", "13.SEP.95": "yes", "30.DEC.88": "?"}
        assert e.ev["13.SEP.95"] == "T175 log" and e.ev["30.DEC.88"] == ""

    def test_a_cell_that_is_not_unknown_needs_evidence(self):
        with pytest.raises(cm.MatrixError, match="no evidence"):
            cm.parse(_csv(_row(ev_a="")))

    def test_unknown_needs_none(self):
        assert cm.parse(_csv(_row(c="?", ev_c="")))["ILFPACK"].fw["30.DEC.88"] == "?"

    def test_a_value_outside_the_four_is_refused(self):
        with pytest.raises(cm.MatrixError, match="fw_13.SEP.95"):
            cm.parse(_csv(_row(a="maybe")))

    def test_the_kind_is_checked(self):
        with pytest.raises(cm.MatrixError, match="kind"):
            cm.parse(_csv(_row(kind="odd")))

    def test_names_are_upper_case_unique_and_sorted(self):
        with pytest.raises(cm.MatrixError, match="upper case"):
            cm.parse(_csv(_row(name="Ilfpack")))
        with pytest.raises(cm.MatrixError, match="twice"):
            cm.parse(_csv(_row(), _row()))
        with pytest.raises(cm.MatrixError, match="not sorted"):
            cm.parse(_csv(_row(name="USERS"), _row(name="PACLEN")))

    def test_an_effect_column_per_release_follows_the_evidence_columns(self):
        assert cm.COLUMNS[-4:] == ("fx_01.AUG.91", "fx_13.SEP.95", "fx_30.DEC.88", "note")

    def test_an_effect_is_kept_and_round_trips(self):
        text = _csv(_row(name="TRANS", kind="danger", fx_a="enters transparent mode; exit 3xCtrl-C/CMDTIME"))
        e = cm.parse(text)["TRANS"]
        assert e.fx == {"01.AUG.91": "", "13.SEP.95": "enters transparent mode; exit 3xCtrl-C/CMDTIME",
                        "30.DEC.88": ""}
        assert cm.to_csv(cm.parse(text)) == text

    def test_an_effect_needs_a_measured_cell(self):
        with pytest.raises(cm.MatrixError, match="fx_30.DEC.88"):
            cm.parse(_csv(_row(c="?", fx_c="prints banner")))

    def test_the_columns_are_fixed(self):
        with pytest.raises(cm.MatrixError, match="columns"):
            cm.parse("name,abbrev\nA,B\n")

    def test_round_trip_is_canonical(self):
        text = _csv(_row(name="ARQTOL", abbrev="ARQTO"), _row())
        assert cm.to_csv(cm.parse(text)) == text


class TestReader:

    @pytest.fixture(autouse=True)
    def _file(self, tmp_path, monkeypatch):
        path = tmp_path / "matrix.csv"
        path.write_text(_csv(
            _row(name="ARQTOL", abbrev="ARQTO", host="", kind="param", a="yes", b="no",
                 ev_a="fw_scan 20260728", ev_b="T155 / T168"),
            _row(name="TRANS", abbrev="T", host="", kind="danger", a="?", b="?", c="?",
                 ev_a="", ev_b="")), encoding="utf-8")
        monkeypatch.setattr(cm, "DATA_FILE", path)
        cm.reload()
        yield
        cm.reload()

    def test_exists(self):
        assert cm.exists("ARQTOL", "13.SEP.95") == "yes"
        assert cm.exists("arqtol", "01.AUG.91") == "no"
        assert cm.exists("ARQTOL", "30.DEC.88") == "?"

    def test_unknown_name_or_release_is_unknown(self):
        assert cm.exists("NOSUCH", "13.SEP.95") == "?"
        assert cm.exists("ARQTOL", "99.XXX.99") == "?"
        assert cm.exists("ARQTOL", None) == "?"

    def test_evidence_kind_host_entry(self):
        assert cm.evidence("ARQTOL", "01.AUG.91") == "T155 / T168"
        assert cm.evidence("ARQTOL", "30.DEC.88") == ""
        assert cm.kind("TRANS") == "danger" and cm.kind("NOSUCH") is None
        assert cm.host("ARQTOL") is None
        assert cm.entry("ARQTOL").abbrev == "ARQTO" and cm.entry("NOSUCH") is None


class TestShippedFile:

    def test_it_loads_and_is_canonical(self):
        text = cm.DATA_FILE.read_text(encoding="utf-8")
        assert cm.to_csv(cm.parse(text)) == text.replace("\r\n", "\n")


class TestGeneratedView:
    """docs/COMMAND_MATRIX.md is generated from the data file; a stale copy fails."""

    @staticmethod
    def _tool():
        import sys
        from pathlib import Path
        tools = Path(__file__).resolve().parents[3] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        import gen_command_matrix
        return gen_command_matrix

    def test_the_view_is_up_to_date(self):
        tool = self._tool()
        want = tool.render(cm.load())
        have = tool.VIEW_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert have == want, (
            "docs/COMMAND_MATRIX.md is stale - run: python tools/gen_command_matrix.py --update")

    def test_the_counts_add_up(self):
        tool = self._tool()
        entries = cm.parse(_csv(_row(), _row(name="USERS", abbrev="US", host="UR", a="no", ev_a="x")))
        text = tool.render(entries)
        assert "2 commands." in text
        assert "| 13.SEP.95 | A | 1 | 1 | 0 | 0 |" in text


class TestReleasesComeFromTheFile:
    """P90 Teil D: an external operator's firmware adds columns (fw_/ev_/fx_<release>), so the list of
    releases is the header of the data file, not a constant."""

    EXT = "12.MAR.93"

    @staticmethod
    def _header(releases):
        return ",".join(cm.columns(releases))

    def _text(self, releases, *rows):
        return "\n".join([self._header(releases), *rows]) + "\n"

    def test_the_columns_follow_the_releases(self):
        cols = cm.columns(("01.AUG.91", "12.MAR.93"))
        assert cols[7:9] == ("fw_01.AUG.91", "fw_12.MAR.93")
        assert cols[-3:] == ("fx_01.AUG.91", "fx_12.MAR.93", "note")
        assert cm.columns(cm.RELEASES) == cm.COLUMNS

    def test_a_file_with_four_releases_is_read_and_written_back(self):
        rels = cm.RELEASES + (self.EXT,)
        row = ",".join(["ILFPACK", "IL", "IL", "param", "ON", "x", "timewave",
                        "yes", "yes", "?", "?", "T1", "T2", "", "", "", "", "", "", ""])
        text = self._text(rels, row)
        entries = cm.parse(text)
        assert tuple(entries["ILFPACK"].fw) == rels
        assert entries["ILFPACK"].fw[self.EXT] == "?"
        assert cm.to_csv(entries) == text

    def test_a_release_that_is_not_the_banner_format_is_refused(self):
        with pytest.raises(cm.MatrixError, match="DD.MMM.YY"):
            cm.parse(self._text(("01.AUG.91", "12.03.1993")))

    def test_the_three_column_groups_must_agree(self):
        header = self._header(cm.RELEASES).replace("ev_13.SEP.95", "ev_13.SEP.96")
        with pytest.raises(cm.MatrixError, match="columns"):
            cm.parse(header + "\n")

    def test_add_release_appends_empty_columns_to_every_row(self):
        entries = cm.parse(_csv(_row()))
        new = cm.add_release(entries, self.EXT)
        e = new["ILFPACK"]
        assert (e.fw[self.EXT], e.ev[self.EXT], e.fx[self.EXT]) == ("?", "", "")
        assert e.fw["01.AUG.91"] == "yes" and tuple(e.fw)[-1] == self.EXT

    def test_add_release_refuses_a_known_or_malformed_release(self):
        entries = cm.parse(_csv(_row()))
        with pytest.raises(cm.MatrixError, match="already"):
            cm.add_release(entries, "01.AUG.91")
        with pytest.raises(cm.MatrixError, match="DD.MMM.YY"):
            cm.add_release(entries, "1993-03-12")

    def test_the_module_follows_the_data_file(self, tmp_path, monkeypatch):
        rels = cm.RELEASES + (self.EXT,)
        row = ",".join(["ILFPACK", "IL", "IL", "param", "ON", "x", "timewave",
                        "yes", "yes", "?", "yes", "T1", "T2", "", "T3", "", "", "", "", "", ""])
        path = tmp_path / "matrix.csv"
        path.write_text(self._text(rels, row), encoding="utf-8")
        monkeypatch.setattr(cm, "DATA_FILE", path)
        cm.reload()
        try:
            assert cm.RELEASES == rels and cm.COLUMNS == cm.columns(rels)
            assert cm.exists("ILFPACK", self.EXT) == "yes"
            assert cm.evidence("ILFPACK", self.EXT) == "T3"
        finally:
            monkeypatch.undo()
            cm.reload()
        assert self.EXT not in cm.RELEASES

    def test_save_writes_the_new_columns_and_reload_sees_them(self, tmp_path, monkeypatch):
        path = tmp_path / "matrix.csv"
        path.write_text(_csv(_row()), encoding="utf-8")
        monkeypatch.setattr(cm, "DATA_FILE", path)
        cm.reload()
        try:
            cm.save(cm.add_release(cm.load(), self.EXT))
            assert self.EXT in cm.RELEASES
            assert f"fw_{self.EXT}" in path.read_text(encoding="utf-8").splitlines()[0]
        finally:
            monkeypatch.undo()
            cm.reload()
