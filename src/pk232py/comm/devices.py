# pk232py - Modern multimode terminal for AEA PK-232 / PK-232MBX TNC
# Copyright (C) 2026  OE3GAS  -  GPL v2
"""comm/devices.py - the known TNC units and the release FINGERPRINT (P78 A).

Qt-free. The firmware release normally comes from the power-on banner
(SerialManager.tnc_release). When the TNC was already awake at connect time
there is no banner, and P72 treats an unknown release as "not verified" - it
then sets NOTHING in Host Mode (T162, device B: "not verified for Host Mode on
unknown"). The PK-232 has no local VERSION command (docs/PK232_firmware_matrix.md
section 1) and RESTART would drop connections, so the release is INFERRED from
one measured difference between the firmware generations:

    EXPERT   verbose              Host (EX query)
    B  01.AUG.91   ?What?          error code $07      (T151, T155)
    A  13.SEP.95   ON / OFF        EXY / EXN           (T151 22:07, T152, T158)
    C  30.12.1988  not measured    not measured

The inference holds ONLY as long as KNOWN_DEVICES lists exactly one unit per
behaviour (docs/DEVICES.md): a second unit of the same generation makes the
fingerprint ambiguous - infer_release() then answers None, never a guess.
Device C is deliberately unmeasured, so it can never be inferred.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union

from pk232py.comm.host_params import host_error_code

SOURCE_BANNER = "banner"
SOURCE_INFERRED = "inferred"


@dataclass(frozen=True)
class KnownDevice:
    label: str                  # "A" / "B" / "C" (docs/DEVICES.md)
    generation: str             # PACTOR / MBX / BASE
    release: str                # exactly as the banner prints it
    expert: Optional[str]       # "present" / "absent" / None = not measured
    # P85: verbose command names the firmware answers with ?What? (the upload
    # leaves them out). frozenset() = measured, none; None = not measured.
    unknown_verbose: Optional[frozenset] = None
    unknown_evidence: str = ""  # testplan numbers behind unknown_verbose


# docs/DEVICES.md - keep the two in step.
KNOWN_DEVICES: tuple = (
    # A: no ?What? at the upload (T161, 20261003_145006; FULLDP removed in P73).
    KnownDevice("A", "PACTOR", "13.SEP.95", "present", frozenset(), "T161"),
    # B: ?What? with banner for EXPERT (ON and OFF), MYPTCALL, PTHUFF, PT200,
    # PTOVER, ARQTOL, MOPT - T168 A/B/C (20261003_220612, 20261004_124240,
    # 20261004_122301), T155, T160.
    KnownDevice("B", "MBX", "01.AUG.91", "absent",
                frozenset({"EXPERT", "MYPTCALL", "PTHUFF", "PT200", "PTOVER",
                           "ARQTOL", "MOPT"}),
                "T155, T160, T168"),
    # C: never connected through the app - unmeasured (None), so everything is sent.
    KnownDevice("C", "BASE", "30.12.1988", None, None, ""),
)

_VALUE_RE = re.compile(r"\b(ON|OFF)\b", re.IGNORECASE)


def expert_behaviour(answer: Union[str, bytes, None]) -> Optional[str]:
    """What an EXPERT query answered: "absent" (unknown command: verbose
    ``?What?``, Host error $07), "present" (a value: ON/OFF, Host Y/N) or
    None (nothing usable - silence, another error code, garbage)."""
    if not answer:
        return None
    if isinstance(answer, bytes):
        code = host_error_code(answer)
        if code is not None:
            return "absent" if code == 0x07 else None
        if answer.startswith(b"EX") and answer[2:] in (b"Y", b"N"):
            return "present"
        answer = answer.decode("ascii", errors="replace")
    if "?what?" in answer.lower():
        return "absent"
    if _VALUE_RE.search(answer):
        return "present"
    return None


def infer_release(expert_answer: Union[str, bytes, None]) -> Optional[tuple]:
    """(release, "inferred") for the one known device whose EXPERT behaviour
    matches *expert_answer*, else None (unusable answer, several devices
    match, or none does)."""
    behaviour = expert_behaviour(expert_answer)
    if behaviour is None:
        return None
    matches = [d for d in KNOWN_DEVICES if d.expert == behaviour]
    if len(matches) != 1:
        return None
    return matches[0].release, SOURCE_INFERRED


def _device_for(release: Optional[str]) -> Optional[KnownDevice]:
    return next((d for d in KNOWN_DEVICES if d.release == release), None)


def unknown_commands(release: Optional[str]) -> Optional[frozenset]:
    """P85: verbose command names *release* does not know, or None when the
    release is unknown or unmeasured (the caller then sends everything)."""
    device = _device_for(release)
    return device.unknown_verbose if device else None


def unsupported_note(release: Optional[str]) -> str:
    """Tooltip text for a setting *release* does not support (P85 C)."""
    device = _device_for(release)
    evidence = f" ({device.unknown_evidence})" if device and device.unknown_evidence else ""
    return f"Not supported by firmware {release}{evidence}"
