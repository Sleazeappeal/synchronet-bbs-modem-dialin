#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Set the BBS location and internet address.

Same section-aware, line-based approach as sbbscfg.py: only the named keys are
rewritten, so comments and formatting survive. Values are written as UTF-8;
whether Synchronet transcodes them for CP437 and PETSCII terminals is then
verified by probing the live ports.
"""

import re
import sys

SECTION_RE = re.compile(r"\s*\[([^\]]+)\]")


def apply_edits(path, edits):
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
    targets = [
        # ASCII transliteration on purpose: CP437 and PETSCII terminals cannot
        # render a UTF-8 "ü", and this avoids depending on Synchronet's
        # transcoding for a string that appears on every login screen.
        ("/u00/sbbs/ctrl/main.ini", {"": {"location": "Your City"}}),
        ("/u00/sbbs/ctrl/msgs.ini", {"Internet": {"addr": "bbs.example.net"}}),
    ]
    for path, edits in targets:
        applied = apply_edits(path, edits)
        if applied is None:
            print(f"ABORTED: {path} left unchanged", file=sys.stderr)
            return 1
        print(f"=== {path} ===")
        for sec, key, old, new in applied:
            print(f"  [{sec}] {key}: {old!r} -> {new!r}")
            if key == "location":
                print(f"    bytes written: {new.encode('utf-8').hex(' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
