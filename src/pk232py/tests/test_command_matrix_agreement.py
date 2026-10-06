# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""P88 Teil E - what the code already knows about the firmware must not contradict the
command matrix. (Deriving the code FROM the matrix is a follow-up package after T179; until
then this test is the guard.) A failing line here is a contradiction to settle with
evidence, never to hide: change the code or add the newer evidence to the matrix."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from pk232py.comm import command_matrix as cm
from pk232py.comm import devices
from pk232py.comm.devices import KNOWN_DEVICES
from pk232py.comm.host_params import HOST_PARAMS, verified_sources
from pk232py.comm.mnemonic_registry import REGISTRY

REPO = Path(cm.__file__).resolve().parents[3]
A, B = "13.SEP.95", "01.AUG.91"

# The application's name for a command is sometimes an abbreviation of the real one.
ALIAS = {"MOPT": "MOPTT"}


def _name(app_name: str) -> str:
    return ALIAS.get(app_name, app_name)


def test_the_devices_table_and_the_matrix_know_the_same_releases():
    # the column order of the matrix (B, A, C) is the spec's, devices.py lists A, B, C
    assert {d.release for d in KNOWN_DEVICES} <= set(cm.RELEASES)


class TestDevicesUnknownVerbose:

    @pytest.mark.parametrize("device", KNOWN_DEVICES, ids=lambda d: d.label)
    def test_every_command_a_firmware_does_not_know_is_no_in_the_matrix(self, device):
        for name in sorted(device.unknown_verbose or ()):
            assert cm.exists(_name(name), device.release) == "no", (
                f"devices.unknown_verbose says {device.label} ({device.release}) does not know "
                f"{name}, the matrix says {cm.exists(_name(name), device.release)!r}")

    def test_a_device_without_an_unknown_list_claims_nothing(self):
        # unknown_verbose None = "send everything" (the upload filter has no measurement for it); the
        # matrix may know more by now (device C after T180) - then deriving the list from it is the
        # follow-up package, not a contradiction
        for d in KNOWN_DEVICES:
            if d.unknown_verbose is None:
                assert devices.unknown_commands(d.release) is None


class TestHostParams:

    def test_every_host_param_is_a_matrix_command(self):
        missing = [p.name for p in HOST_PARAMS if cm.entry(_name(p.name)) is None]
        assert not missing, f"host_params names not in the matrix: {missing}"

    def test_a_verified_parameter_exists_on_that_release(self):
        wrong = []
        for p in HOST_PARAMS:
            for release in p.verified_releases:
                if cm.exists(_name(p.name), release) not in ("yes", "expert"):
                    wrong.append(f"{p.name} {release}: matrix says {cm.exists(_name(p.name), release)!r}")
        assert not wrong, wrong

    def test_the_host_mnemonic_agrees(self):
        wrong = []
        for p in HOST_PARAMS:
            if not p.mnemonic or not p.verified_releases:
                continue
            host = cm.host(_name(p.name))
            if host != p.mnemonic.decode("ascii"):
                wrong.append(f"{p.name}: host_params {p.mnemonic!r}, matrix {host!r}")
        assert not wrong, wrong

    def test_the_evidence_of_host_params_is_in_the_matrix_cell(self):
        for p in HOST_PARAMS:
            for release, tests in verified_sources(p.name).items():
                evidence = cm.evidence(_name(p.name), release)
                for test in tests.split(", "):
                    assert test in evidence, f"{p.name} {release}: {test} missing in {evidence[:80]!r}"


class TestMnemonicRegistry:

    def test_a_measured_mnemonic_is_the_host_entry_of_its_command(self):
        wrong = []
        for mn, entry in REGISTRY.items():
            if not entry.evidence:
                continue
            name = entry.meaning.split()[0].rstrip(";").upper()
            e = cm.entry(name)
            if e is None:
                wrong.append(f"{mn!r}: no matrix command {name}")
            elif e.host != mn.decode("ascii"):
                wrong.append(f"{name}: registry {mn!r}, matrix host {e.host!r}")
            else:
                for release in entry.evidence:
                    if e.fw[release] not in ("yes", "expert"):
                        wrong.append(f"{name} {release}: registry has evidence, matrix says {e.fw[release]!r}")
        assert not wrong, wrong


class TestRawScan:

    def test_the_raw_scan_of_device_a_agrees_with_the_matrix(self):
        path = REPO / "docs" / "reference" / "fw_scan" / "20260728_deviceA_13SEP95.csv"
        wrong = []
        with open(path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                name, result = row["name"], row["result"]
                if name in ("AMOTR", "TRANS", "CALIBRATE"):      # see the .md next to the file
                    continue
                want = "expert" if name in ("TRFLOW", "XFLOW") else "yes"
                if result != "SUPPORTED" and want == "yes":
                    wrong.append(f"{name}: scan result {result}")
                elif cm.exists(name, A) not in (want, "expert"):
                    wrong.append(f"{name}: scan {result}, matrix {cm.exists(name, A)!r}")
        assert not wrong, wrong

    def test_a_cell_is_no_somewhere_only_with_matching_evidence(self):
        for name, e in cm.all_entries().items():
            for release, value in e.fw.items():
                if value == "no":
                    assert e.ev[release], f"{name} {release}: no without evidence"
