#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Probe Synchronet's RLogin ports to validate the softmodem relay design.

Checks two things that the whole dial-in path depends on:

  1. Byte transparency. Synchronet sets TELNET_MODE_OFF for RLogin sessions,
     so the stream should contain no IAC (0xFF) command sequences and no
     doubled 0xFF. If that holds, the relay needs no escaping logic at all --
     it is a straight splice after the handshake.

  2. Terminal mode selection by port. Port 2300 should answer as an 80-column
     ANSI/CP437 session, port 2340 (Pet40Port) as 40-column PETSCII.

Usage: bbs-rlogin-probe.py <port> [term]
"""

import socket
import sys
import time

IAC = 0xFF


def rlogin_handshake(term):
    # RFC 1282: NUL, client-user NUL, server-user NUL, terminal/speed NUL.
    # Both user fields are left empty: Synchronet's AUTO_LOGON is deliberately
    # NOT enabled, so these must not be able to authenticate anyone.
    return b"\x00" + b"\x00" + b"\x00" + term.encode("ascii") + b"\x00"


def probe(port, term, seconds=4.0):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(rlogin_handshake(term))

    data = bytearray()
    s.settimeout(1.0)
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        data.extend(chunk)
    s.close()
    return bytes(data)


def analyse(port, term, data):
    print(f"=== port {port} (term={term!r}) ===")
    print(f"bytes received: {len(data)}")

    if not data:
        print("  !! no data -- connection produced nothing")
        return

    # RFC 1282: the server acknowledges the handshake with a single NUL.
    print(f"  first byte: {data[0]:#04x}" + ("  (NUL ack, as per RFC 1282)" if data[0] == 0 else ""))

    ff_positions = [i for i, b in enumerate(data) if b == IAC]
    print(f"  0xFF bytes: {len(ff_positions)}")
    iac_cmds = 0
    doubled = 0
    for i in ff_positions:
        nxt = data[i + 1] if i + 1 < len(data) else None
        if nxt is None:
            continue
        if nxt == IAC:
            doubled += 1
        elif nxt in (0xFB, 0xFC, 0xFD, 0xFE, 0xFA, 0xF0):  # WILL/WONT/DO/DONT/SB/SE
            iac_cmds += 1
    print(f"  IAC command sequences: {iac_cmds}")
    print(f"  doubled 0xFF (telnet escaping): {doubled}")
    if iac_cmds == 0 and doubled == 0:
        print("  => stream is byte-transparent; relay needs no escaping")
    else:
        print("  => TELNET ESCAPING PRESENT; relay would need IAC handling")

    text = data.decode("cp437", errors="replace")
    printable = "".join(ch if ch.isprintable() or ch in "\r\n" else "." for ch in text)
    print("  --- first 300 chars (CP437-decoded) ---")
    print("  " + printable[:300].replace("\n", "\n  "))
    print()


if __name__ == "__main__":
    port = int(sys.argv[1])
    term = sys.argv[2] if len(sys.argv) > 2 else "ansi-bbs/2400"
    analyse(port, term, probe(port, term))
