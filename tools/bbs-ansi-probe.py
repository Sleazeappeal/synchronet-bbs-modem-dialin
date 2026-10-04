#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Probe the relay chain as an ANSI terminal, and check 0xFF byte transparency.

The plain raw probe does not answer Synchronet's terminal-detection sequences,
so the BBS falls back to DUMB/US-ASCII and never sends real CP437 art. That
leaves the one thing the relay design has to get right untested: CP437 0xFF is
a non-trimmed blank that ANSI artists use deliberately, and over telnet a server
must transmit it doubled. If anything in the chain were doing telnet escaping,
every 0xFF would arrive twice and the art would shift.

This answers the detection sequences so the BBS commits to ANSI/CP437, then
reports how the 0xFF bytes actually arrived.

Answers:
  ESC[0c  Device Attributes      -> ESC[?1;2c   (VT100 with AVO)
  ESC[6n  Cursor Position Report -> ESC[<r>;<c>R

Synchronet sizes the screen by cursoring far down and right and then asking
where the cursor ended up, so the reported position is what sets the terminal
dimensions.

Usage: bbs-ansi-probe.py <port> [seconds] [rows] [cols]
"""

import re
import socket
import sys
import time

DA_QUERY = b"\x1b[0c"
CPR_QUERY = b"\x1b[6n"


def run(port, seconds, rows, cols):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.settimeout(0.5)
    data = bytearray()
    pending = bytearray()
    answers = {"da": 0, "cpr": 0}
    deadline = time.time() + seconds

    while time.time() < deadline:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        data.extend(chunk)
        pending.extend(chunk)

        # Answer any queries seen so far. Keep a short tail in case a sequence
        # is split across two reads.
        while DA_QUERY in pending:
            pending = pending.split(DA_QUERY, 1)[1]
            s.sendall(b"\x1b[?1;2c")
            answers["da"] += 1
        while CPR_QUERY in pending:
            pending = pending.split(CPR_QUERY, 1)[1]
            s.sendall(f"\x1b[{rows};{cols}R".encode("ascii"))
            answers["cpr"] += 1
        if len(pending) > 8:
            pending = pending[-8:]

    s.close()
    return bytes(data), answers


def main():
    port = int(sys.argv[1])
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 24
    cols = int(sys.argv[4]) if len(sys.argv) > 4 else 80

    data, answers = run(port, seconds, rows, cols)
    print(f"=== ANSI probe on port {port} ({rows}x{cols}) ===")
    print(f"bytes received: {len(data)}")
    print(f"answered: {answers['da']} device-attribute, "
          f"{answers['cpr']} cursor-position queries")

    ff = [i for i, b in enumerate(data) if b == 0xFF]
    doubled = sum(1 for i in ff if i + 1 < len(data) and data[i + 1] == 0xFF)
    iac_cmds = sum(1 for i in ff
                   if i + 1 < len(data)
                   and data[i + 1] in (0xF0, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE))
    print(f"0xFF bytes: {len(ff)}   adjacent pairs: {doubled}   "
          f"IAC-like sequences: {iac_cmds}")

    if not ff:
        print("  (no 0xFF in this sample -- inconclusive, not a pass)")
    elif doubled == 0 and iac_cmds == 0:
        print("  => 0xFF arrives single and unescaped: byte-transparent")
    else:
        print("  => 0xFF ARRIVES DOUBLED OR ESCAPED: art will be misaligned")

    # Show what the BBS decided about the terminal.
    text = data.decode("cp437", errors="replace")
    for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        if "TERM:" in line or "CONN:" in line:
            print("  " + "".join(c for c in line if c.isprintable()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
