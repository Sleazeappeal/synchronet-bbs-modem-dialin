#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Raw TCP to Synchronet RLogin relay for softmodem dial-in lines.

Asterisk's Softmodem() application opens a plain TCP connection and passes
bytes through untouched -- no telnet protocol handling of any kind. Synchronet
has no raw listener, but it does set TELNET_MODE_OFF for RLogin sessions, which
makes an RLogin session byte-transparent: no IAC commands, no 0xFF doubling.

That matters because CP437 0xFF (a non-trimmed blank used deliberately in ANSI
art) and PETSCII 0xFF (the pi glyph) both occur in ordinary BBS screens, and
ZMODEM payloads are full of 0xFF. Over telnet those would arrive doubled.

So this relay speaks RLogin upstream and raw bytes downstream, and after the
handshake it performs no transformation whatsoever:

    accept -> connect upstream -> send RFC 1282 handshake
           -> swallow the one-byte NUL acknowledgement
           -> splice both directions verbatim until either side closes

One instance per terminal mode. The listening port is the upstream port plus
one, and the terminal type/speed string is fixed per instance because the line's
modulation is fixed -- Softmodem() cannot report a negotiated rate.

Usage:
    sbbs-relay.py --listen 2301 --upstream 2300 --term ansi-bbs/2400
    sbbs-relay.py --listen 2341 --upstream 2340 --term petscii/1200
"""

import argparse
import asyncio
import logging
import sys

LOG = logging.getLogger("sbbs-relay")

# RFC 1282 acknowledgement: the server replies with a single zero byte once it
# has read the handshake.
ACK = b"\x00"


def build_handshake(term: str) -> bytes:
    """RFC 1282: NUL, client-user NUL, server-user NUL, terminal/speed NUL.

    Both user fields are sent empty on purpose. Synchronet's AUTO_LOGON option
    would authenticate an RLogin client as whatever name appears here, so a
    non-empty value combined with that option being switched on would log every
    caller in as that user without a password. Empty keeps the BBS asking.
    """
    return b"\x00" + b"\x00" + b"\x00" + term.encode("ascii") + b"\x00"


async def splice(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Copy bytes one way, verbatim, until EOF."""
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        # Half-close so the peer sees EOF; the other direction may still drain.
        try:
            writer.write_eof()
        except (OSError, RuntimeError):
            pass


class Relay:
    def __init__(self, upstream_host: str, upstream_port: int, term: str,
                 handshake_timeout: float):
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.term = term
        self.handshake_timeout = handshake_timeout
        self.sessions = 0

    async def handle(self, down_reader: asyncio.StreamReader,
                     down_writer: asyncio.StreamWriter) -> None:
        peer = down_writer.get_extra_info("peername")
        self.sessions += 1
        session = self.sessions
        LOG.info("session %d: accepted from %s", session, peer)

        try:
            up_reader, up_writer = await asyncio.open_connection(
                self.upstream_host, self.upstream_port)
        except OSError as exc:
            LOG.error("session %d: upstream %s:%d unreachable: %s",
                      session, self.upstream_host, self.upstream_port, exc)
            down_writer.close()
            return

        try:
            up_writer.write(build_handshake(self.term))
            await up_writer.drain()

            # Consume exactly the acknowledgement byte and nothing more, so the
            # first byte of the BBS banner is not swallowed with it.
            ack = await asyncio.wait_for(up_reader.readexactly(1),
                                         timeout=self.handshake_timeout)
            if ack != ACK:
                LOG.warning("session %d: unexpected handshake reply %r "
                            "(expected NUL); passing it through", session, ack)
                down_writer.write(ack)
                await down_writer.drain()
        except (asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
            LOG.error("session %d: no handshake acknowledgement: %s", session, exc)
            up_writer.close()
            down_writer.close()
            return
        except OSError as exc:
            LOG.error("session %d: handshake failed: %s", session, exc)
            up_writer.close()
            down_writer.close()
            return

        LOG.info("session %d: connected to %s:%d as %s",
                 session, self.upstream_host, self.upstream_port, self.term)

        # From here on: no transformation, in either direction. A dropped call
        # must free the BBS node -- and hang up the SIP channel -- immediately
        # rather than leaving it wedged. Waiting for *both* directions to hit
        # EOF (as asyncio.gather does) is wrong: if the far end (say, the
        # physical modem) never sends another byte once Synchronet has gone
        # away, that direction blocks forever on read() and the other socket
        # is never actually closed -- only half-closed by splice()'s
        # write_eof(). Softmodem() does not treat a half-close as hangup, so
        # the Asterisk channel -- and with it the analog line -- stays up
        # indefinitely. Closing both sockets the moment either direction ends
        # gives Softmodem() a real closed connection to detect.
        tasks = [
            asyncio.create_task(splice(down_reader, up_writer)),
            asyncio.create_task(splice(up_reader, down_writer)),
        ]
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        for t in pending:
            try:
                await t
            except asyncio.CancelledError:
                pass

        for w in (up_writer, down_writer):
            try:
                w.close()
            except OSError:
                pass
        LOG.info("session %d: closed", session)


async def main_async(args: argparse.Namespace) -> int:
    relay = Relay(args.upstream_host, args.upstream, args.term,
                  args.handshake_timeout)
    server = await asyncio.start_server(
        relay.handle, args.listen_host, args.listen)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    LOG.info("listening on %s -> %s:%d (term=%s)",
             addrs, args.upstream_host, args.upstream, args.term)
    async with server:
        await server.serve_forever()
    return 0


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--listen", type=int, required=True,
                   help="TCP port to accept Softmodem() connections on")
    p.add_argument("--listen-host", default="127.0.0.1",
                   help="address to listen on (default: 127.0.0.1)")
    p.add_argument("--upstream", type=int, required=True,
                   help="Synchronet RLogin port to connect to")
    p.add_argument("--upstream-host", default="127.0.0.1",
                   help="Synchronet host (default: 127.0.0.1)")
    p.add_argument("--term", default="ansi-bbs/2400",
                   help="RLogin terminal type/speed, e.g. ansi-bbs/2400")
    p.add_argument("--handshake-timeout", type=float, default=10.0,
                   help="seconds to wait for the RLogin acknowledgement")
    p.add_argument("--log-level", default="INFO")
    return p.parse_args(argv)


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(message)s", stream=sys.stderr)
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
