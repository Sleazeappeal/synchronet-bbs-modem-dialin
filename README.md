# Synchronet BBS dial-in with real modems over VoIP

## Credits

This setup is glue around other people's work:

- **[Synchronet BBS](https://www.synchro.net/)** by **Rob Swindell**
  (Digital Dynamics). `config/systemd/sbbs.service` is adapted from the unit
  Synchronet ships.
- **[Asterisk](https://www.asterisk.org/)** (Sangoma), and
  **[FreePBX](https://www.freepbx.org/)** as the PBX the lines register to.
- **app_softmodem** by **Christian Groeger**
  ([proquar/asterisk-Softmodem](https://github.com/proquar/asterisk-Softmodem)),
  with work by **Rob O'Donnell** and **Naveen Albert**
  ([InterLinked1/phreakscript](https://github.com/InterLinked1/phreakscript)),
  based on `app_fax.c` by **Dmitry Andrianov** and **Steve Underwood**. The V.42
  version used here is
  [Sleazeappeal/app_softmodem_v42](https://github.com/Sleazeappeal/app_softmodem_v42),
  which lists the credits in full.
- **[spandsp](https://github.com/freeswitch/spandsp)** by **Steve Underwood**,
  which does the actual modem signal processing.

Thank you to all of them.

The configuration, the relay, the scripts and this documentation were written
with **Claude Opus 5.5** (Anthropic), working in Claude Code, together with the
repository owner, who built and runs the BBS and did all the testing with the
real modems and retro computers.

## What this is

Retro computers dial a BBS with their own modems, as in the 1990s, but the
"phone line" is a VoIP setup in a home lab:

```
  Retro PC / C64 ── modem ── ATA ── SIP PBX (FreePBX)
                                        │  SIP + RTP (G.711 ulaw)
  ┌─────────────────────────────────────┼──────────────────────────────┐
  │ BBS host (Debian)              Asterisk (registered SIP client,    │
  │                                one extension per line)             │
  │                                     │ Softmodem() per call         │
  │                         raw TCP ────┴──── raw TCP                  │
  │                      relay :2301          relay :2341              │
  │                   RLogin :2300            RLogin :2340             │
  │                      └──── Synchronet BBS ────┘                    │
  │                     ANSI / CP437 80 col   PETSCII 40 col           │
  └────────────────────────────────────────────────────────────────────┘
```

- Asterisk does nothing but answer the call and turn it into a TCP stream:
  `app_softmodem` demodulates V.22bis (2400 bit/s) or V.22 (1200 bit/s), with
  **V.42 error correction and V.42bis compression** for modems that support
  them.
- A tiny **relay** speaks RLogin to Synchronet, because an RLogin session is
  byte-transparent (no telnet IAC escaping, so ANSI art with 0xFF, PETSCII and
  ZMODEM pass through untouched) and the port decides the terminal mode.
- Each line is its own PBX extension; the caller picks ANSI or PETSCII by
  the number they dial, the way BBSes used to advertise separate lines.

Tested with Rockwell, USRobotics, Smart Link and Conexant modems behind
Grandstream HT802 and Cisco SPA112 ATAs: logins, ANSI art, ZMODEM/YMODEM
transfers both ways.

## Contents

| Path | What | Installed as |
|---|---|---|
| `INSTALL.md` | step-by-step installation, PBX and ATA settings, troubleshooting | — |
| `relay/sbbs-relay.py` | raw TCP ↔ RLogin relay | `/usr/local/bin/sbbs-relay.py` |
| `config/default/sbbs-relay-*` | relay profiles (ANSI, PETSCII) | `/etc/default/` |
| `config/systemd/` | units for Synchronet, Asterisk, the relay, the backup | `/etc/systemd/system/` |
| `config/asterisk/` | minimal Asterisk configuration, `pjsip.conf.example` | `/usr/local/etc/asterisk/` |
| `config/logrotate/asterisk` | log rotation for the source-built Asterisk | `/etc/logrotate.d/asterisk` |
| `config/rsyslog/60-remote.conf` | optional log forwarding | `/etc/rsyslog.d/` |
| `scripts/sbbscfg.py`, `set_identity.py`, `enable_web.py` | apply the identity and port map to Synchronet's ini files | run once |
| `scripts/bbs-backup.sh` | nightly application-level backup | `/usr/local/sbin/bbs-backup.sh` |
| `tools/` | probes for the RLogin ports and the relay | — |

## Requirements

- A Debian 13 machine or VM (2 vCPU, 2 GB RAM were plenty), with a stable LAN
  address.
- A SIP PBX on the same LAN with one extension per BBS line (FreePBX 17 here).
- Callers: modems on ATAs that register to the same PBX.
- Asterisk 22 built from source with the patched `app_softmodem` and spandsp
  from [app_softmodem_v42](https://github.com/Sleazeappeal/app_softmodem_v42).
- Synchronet 3.22 built from source.

See [INSTALL.md](INSTALL.md).

## License

GNU General Public License version 2 (`LICENSE`).
