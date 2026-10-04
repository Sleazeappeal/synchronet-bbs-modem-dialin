#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Connect to a port as raw TCP and report what arrives.

This is what Asterisk's Softmodem() does: open a socket, send nothing, pass
bytes through. Pointed at the relay it proves the caller sees a clean BBS
banner with no handshake residue and no telnet escaping.
"""

import socket
import sys
import time

IAC = 0xFF


def probe(port, seconds=4.0, send=b""):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    if send:
        s.sendall(send)
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


def main():
    port = int(sys.argv[1])
    data = probe(port)
    print(f"=== raw TCP to port {port} ===")
    print(f"bytes received: {len(data)}")
    if not data:
        print("  !! nothing received")
        return 1
    print(f"  first byte: {data[0]:#04x}")
    if data[0] == 0:
        print("  !! leading NUL -- the RLogin ack leaked through to the caller")
    else:
        print("  ok: no leading NUL, handshake ack was consumed by the relay")

    ff = [i for i, b in enumerate(data) if b == IAC]
    iac_cmds = sum(1 for i in ff
                   if i + 1 < len(data) and data[i + 1] in (0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xF0))
    doubled = sum(1 for i in ff if i + 1 < len(data) and data[i + 1] == IAC)
    print(f"  0xFF bytes: {len(ff)}, IAC commands: {iac_cmds}, doubled 0xFF: {doubled}")

    text = data.decode("cp437", errors="replace")
    printable = "".join(c if c.isprintable() or c in "\r\n" else "." for c in text)
    print("  --- first 250 chars ---")
    print("  " + printable[:250].replace("\n", "\n  "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
