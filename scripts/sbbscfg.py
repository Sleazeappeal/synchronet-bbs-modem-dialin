#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Apply the BBS identity and the port map of the modem dial-in setup to
Synchronet's ini files. Edit the identity values in main() first.

Section-aware, line-based editing: only the listed keys are rewritten, so the
comments, ordering, indentation and separator style of the original files are
preserved exactly. Any key that cannot be found is reported as an error rather
than silently appended, so a typo cannot become a missing setting.
"""

import re
import secrets
import string
import sys

CTRL = "/u00/sbbs/ctrl"

SECTION_RE = re.compile(r"\s*\[([^\]]+)\]")


def make_password(length=24):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def apply_edits(path, edits):
    """edits maps section name -> {key: value}. Section "" is the implicit
    top-level section before the first [header]."""
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        lines = f.readlines()

    pending = {sec: dict(kv) for sec, kv in edits.items()}
    current = ""
    out = []
    applied = []

    for line in lines:
        header = SECTION_RE.match(line)
        if header:
            current = header.group(1)
            out.append(line)
            continue

        # [ \t]* rather than \s*: \s matches the trailing newline too, so on a
        # key with an empty value the newline was captured as "space after =",
        # pushing the new value onto its own line and silently corrupting the
        # file. Only horizontal whitespace may be consumed here.
        m = re.match(r"^([ \t]*)([A-Za-z_][A-Za-z0-9_]*)([ \t]*)=([ \t]*)(.*?)[ \t]*$", line)
        if m and current in pending and m.group(2) in pending[current]:
            indent, key, pre, post, old = m.groups()
            new = pending[current].pop(key)
            # A key that was empty has no spacing after "=" to copy; match the
            # surrounding file style instead of emitting "Key =value".
            if not post and pre:
                post = " "
            out.append(f"{indent}{key}{pre}={post}{new}\n")
            applied.append((current or "<top>", key, old, new))
        else:
            out.append(line)

    missing = [(sec, key) for sec, kv in pending.items() for key in kv]
    if missing:
        for sec, key in missing:
            print(f"ERROR: key not found: [{sec or '<top>'}] {key}", file=sys.stderr)
        return None

    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.writelines(out)
    return applied


def main():
    syspass = make_password()

    # Port map. Nothing binds below 1024 and nothing binds off loopback yet;
    # the public SSH and web exposure is a later phase.
    sbbs_edits = {
        "Global": {"Interface": "127.0.0.1"},
        "BBS": {
            # RLogin is the modem path: Synchronet turns telnet mode off for
            # RLogin sessions, so the byte stream is transparent (no IAC).
            "RLoginPort": "2300",                              # ANSI / CP437, 80 col
            "RLoginInterface": "127.0.0.1,127.0.0.1:2340",     # plus the PETSCII 40 port
            "Pet40Port": "2340",
            "Pet80Port": "2380",
            # Telnet is kept on loopback for sysop debugging only.
            "TelnetPort": "2323",
            "TelnetInterface": "127.0.0.1",
            # SSH stays on loopback until the public-access phase.
            "SSHPort": "2222",
            "SSHInterface": "127.0.0.1",
        },
        # Services not in scope; enabled deliberately later if wanted.
        "Mail": {"AutoStart": "false"},
        "FTP": {"AutoStart": "false"},
        "Web": {"AutoStart": "false"},
        "Services": {"AutoStart": "false"},
    }

    main_edits = {
        "": {
            "name": "MyBBS",                # system name
            "qwk_id": "MYBBS",              # QWK ID, up to 8 characters
            "operator": "sysop",            # displayed sysop name
            # CET (0x103C) | DAYLIGHT (0x8000); see smbdefs.h for other zones.
            "timezone": "0x903C",
            "password": syspass,
        }
    }

    # --sbbs-only re-applies the port map without touching main.ini, so a rerun
    # does not regenerate the system password.
    only_sbbs = "--sbbs-only" in sys.argv
    targets = [(f"{CTRL}/sbbs.ini", sbbs_edits)]
    if not only_sbbs:
        targets.append((f"{CTRL}/main.ini", main_edits))

    results = {}
    for path, edits in targets:
        applied = apply_edits(path, edits)
        if applied is None:
            print(f"ABORTED: {path} left unchanged", file=sys.stderr)
            return 1
        results[path] = applied

    # The generated system password is needed for sysop functions in scfg and
    # is used to encrypt the generated SSH host key. Store it readable only by
    # the sbbs user rather than printing it.
    passfile = None
    if not only_sbbs:
        import os
        passfile = f"{CTRL}/.syspass-initial"
        with open(passfile, "w", encoding="ascii") as f:
            f.write(syspass + "\n")
        os.chmod(passfile, 0o600)

    for path, applied in results.items():
        print(f"\n=== {path} ===")
        for sec, key, old, new in applied:
            shown = "<generated, see .syspass-initial>" if key == "password" else new
            print(f"  [{sec}] {key}: {old!r} -> {shown}")
    if passfile:
        print(f"\nSystem password written to {passfile} (mode 0600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
