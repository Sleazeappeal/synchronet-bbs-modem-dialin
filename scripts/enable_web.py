#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Enable Synchronet's web terminal on the LAN for convenient sysop access.

This only turns the [Web] service on, bound to the host's LAN interface on a
non-privileged port, so no capability grant is needed (Synchronet built with
NOCAP=1). Set "Interface" below first. For public access put it behind a
reverse proxy with TLS instead.
"""

import re
import sys

CTRL = "/u00/sbbs/ctrl"

SECTION_RE = re.compile(r"\s*\[([^\]]+)\]")


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

        m = re.match(r"^([ \t]*)([A-Za-z_][A-Za-z0-9_]*)([ \t]*)=([ \t]*)(.*?)[ \t]*$", line)
        if m and current in pending and m.group(2) in pending[current]:
            indent, key, pre, post, old = m.groups()
            new = pending[current].pop(key)
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
    sbbs_edits = {
        "Web": {
            "AutoStart": "true",
            "Interface": "192.0.2.10",  # the host's LAN address -- no TLS
            "Port": "6464",
        },
    }

    path = f"{CTRL}/sbbs.ini"
    applied = apply_edits(path, sbbs_edits)
    if applied is None:
        print(f"ABORTED: {path} left unchanged", file=sys.stderr)
        return 1

    print(f"=== {path} ===")
    for sec, key, old, new in applied:
        print(f"  [{sec}] {key}: {old!r} -> {new!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
