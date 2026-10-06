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
    C  30.DEC.88   ?What?          error code $07?     (T180, verbose measured)

EXPERT alone separates A from the other two, but B and C answer it the same way (T180, device C,
06.10.2026, hw_logs/20261006_fw_scan_C.log): with that answer the release is ambiguous. A SECOND
question tells them apart, and it is DERIVED from the command matrix, not coded here: a command
whose cell is known on every candidate and differs between them (MAILDROP: yes on 01.AUG.91, no on
30.DEC.88; ``discriminating_command()``). It is asked only when EXPERT does not decide.

The inference holds ONLY as long as the matrix has a differing, measured command for the candidates:
no such command, an unusable answer, or two candidates that still match -> infer_release() answers
None, never a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union

from pk232py.comm import command_matrix as cm
from pk232py.comm.host_params import host_error_code

SOURCE_BANNER = "banner"
SOURCE_INFERRED = "inferred"


@dataclass(frozen=True)
class KnownDevice:
    label: str                  # "A" / "B" / "C" (docs/DEVICES.md)
    generation: str             # PACTOR / MBX / BASE
    release: str                # exactly as the banner prints it
    expert: Optional[str]       # "present" / "absent" / None = not measured (agrees with the matrix cell)
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
    # C: banner `Release 30.DEC.88`; EXPERT answers ?What? like B (T180); everything else unmeasured.
    KnownDevice("C", "BASE", "30.DEC.88", "absent", None, ""),
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


def candidate_releases(expert_answer: Union[str, bytes, None]) -> list:
    """The releases whose EXPERT behaviour matches *expert_answer*: [] (unusable answer),
    one release (decided) or several (ambiguous - ask the second question)."""
    behaviour = expert_behaviour(expert_answer)
    if behaviour is None:
        return []
    return [d.release for d in KNOWN_DEVICES if d.expert == behaviour]


def _same(cell: str) -> str:
    return "yes" if cell == "expert" else cell        # present is present, EXPERT or not


def discriminating_command(releases: list, preferred: tuple = ("MAILDROP",)) -> Optional[str]:
    """A command to ask that tells *releases* apart, DERIVED from the command matrix: its cell is
    measured (not ?) on every one of them and differs between them, and it is a plain parameter
    (a bare query changes nothing). *preferred* only orders the choices - MAILDROP is what the
    app already asks for its capability check (detect_maildrop); the matrix still has to say that it
    discriminates. None if no command does."""
    entries = cm.all_entries()

    def discriminates(name: str) -> bool:
        e = entries.get(name)
        if e is None or e.kind != "param":
            return False
        cells = [e.fw.get(r, "?") for r in releases]
        return "?" not in cells and len({_same(c) for c in cells}) > 1

    for name in preferred:
        if discriminates(name):
            return name
    return next((n for n in sorted(entries) if discriminates(n)), None)


def answer_behaviour(command: str, answer: Union[str, bytes, None]) -> Optional[str]:
    """What the answer to a bare query of *command* says: "no" (unknown command: verbose ?What?,
    Host error $07), "yes" (a value, or ?EXPERT command = present but gated) or None (nothing
    usable - silence, only an echo, another error)."""
    if not answer:
        return None
    if isinstance(answer, bytes):
        code = host_error_code(answer)
        if code is not None:
            return "no" if code == 0x07 else None
        mnemonic = (cm.host(command) or "").encode("ascii")
        return "yes" if mnemonic and answer.startswith(mnemonic) and len(answer) > len(mnemonic) else None
    # the answer must START with the echo of this very command (a late answer of another command or
    # stray text is nobody's answer); stale prompts in front of it are skipped
    text = answer.replace("\x11", "").lstrip(" \n\r\x00")
    while text.lower().startswith("cmd:"):
        text = text[4:].lstrip(" \n\r\x00")
    if not text.upper().startswith(command.upper()):
        return None
    rest = text[len(command):].split("cmd:", 1)[0]
    low = rest.lower()
    if "?what?" in low:
        return "no"
    if "?expert" in low:
        return "yes"
    return "yes" if rest.strip() else None


def infer_release(expert_answer: Union[str, bytes, None], second=None) -> Optional[tuple]:
    """(release, "inferred") for the one known device that fits, else None.

    *expert_answer* is the answer to a bare EXPERT query. When it decides (one candidate) that is
    the result. When it does not (B and C both answer ?What?), *second* - a callable
    ``second(command_name) -> answer`` that asks the TNC (verbose or Host Mode, the caller knows how)
    - is called ONCE with the command ``discriminating_command()`` derives from the matrix, and the
    candidate whose matrix cell fits the answer wins. Without *second*, an unusable answer, no
    discriminating command or more than one fitting candidate: None - never a guess."""
    candidates = candidate_releases(expert_answer)
    if len(candidates) == 1:
        return candidates[0], SOURCE_INFERRED
    if len(candidates) < 2 or second is None:
        return None
    command = discriminating_command(candidates)
    if command is None:
        return None
    behaviour = answer_behaviour(command, second(command))
    if behaviour is None:
        return None
    fitting = [r for r in candidates if _same(cm.exists(command, r)) == behaviour]
    return (fitting[0], SOURCE_INFERRED) if len(fitting) == 1 else None


def _device_for(release: Optional[str]) -> Optional[KnownDevice]:
    return next((d for d in KNOWN_DEVICES if d.release == release), None)


def has_pactor(release: Optional[str]) -> Optional[bool]:
    """P85a: does the firmware generation of *release* have PACTOR? None for
    an unknown release (the caller keeps its permissive default)."""
    device = _device_for(release)
    return device.generation == "PACTOR" if device else None


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
