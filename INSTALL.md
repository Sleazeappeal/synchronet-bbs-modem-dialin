# Installation

The order below is the one that worked: BBS first, then the relay, then
Asterisk, then the PBX and the callers' ATAs. Every step can be tested on its
own before the next.

Examples use four lines on extensions 401–404 (three ANSI lines and one
PETSCII line), the PBX at `pbx.example.lan`, and Synchronet in `/u00/sbbs`.

## 1. The host

Debian 13, minimal install. 2 vCPU and 2 GB RAM were plenty. Give it a
**stable LAN address** (static or a DHCP reservation): the SIP registrations
depend on it. Keep the clock synced (timesyncd or chrony).

Nothing in this setup needs to listen on a public interface. Synchronet's
terminal ports and the relays bind to `127.0.0.1`; Asterisk talks SIP and RTP
on the LAN only.

## 2. Synchronet

Build 3.22 from source as an unprivileged `sbbs` user, following the official
[install-sbbs.mk](https://wiki.synchro.net/install:nix) method. Headless, no
GUI tools, and no `setcap` (no port below 1024 is used):

```sh
make -f install-sbbs.mk SBBSDIR=/u00/sbbs SBBSUSER=sbbs SBBSGROUP=sbbs \
     SYMLINK=1 NO_X=1 NO_GTK=1 NOCAP=1
```

Build dependencies used on Debian 13: `zip gdb libarchive-dev libncurses-dev
libnspr4-dev libmosquitto-dev libsystemd-dev libcap-dev python-is-python3
lrzsz gkermit`. (`libncursesw5-dev` from the official list does not exist in
Debian 13; `libncurses-dev` replaces it.)

Then configure it. Edit the identity values in `scripts/sbbscfg.py` (system
name, QWK ID, sysop name, time zone) and `scripts/set_identity.py` (location,
internet address), then, as the `sbbs` user:

```sh
python3 scripts/sbbscfg.py        # identity, port map, generated system password
python3 scripts/set_identity.py   # location and internet address
```

`sbbscfg.py` sets this port map in `ctrl/sbbs.ini` and turns the mail, FTP,
web and services servers off:

| Key | Port | Bind | Purpose |
|---|---|---|---|
| `RLoginPort` | 2300 | 127.0.0.1 | modem path, ANSI / CP437, 80 columns |
| `Pet40Port` | 2340 | 127.0.0.1 | modem path, PETSCII, 40 columns (opened via `RLoginInterface`) |
| `Pet80Port` | 2380 | — | PETSCII 80 columns, not opened |
| `TelnetPort` | 2323 | 127.0.0.1 | sysop debugging only |
| `SSHPort` | 2222 | 127.0.0.1 | for later public SSH access |

The generated system password is written to `ctrl/.syspass-initial` (mode
0600). `scripts/enable_web.py` optionally turns on the web terminal on the
LAN.

Install `config/systemd/sbbs.service` (it sets `SBBSCTRL=/u00/sbbs/ctrl`),
`systemctl enable --now sbbs`, and **register the sysop**: the first account
created gets sysop rights, so log in once as a new user (for example with
`telnet 127.0.0.1 2323`).

Security points:

- Leave `ctrl/rlogin.cfg` **empty** and do not enable `AUTO_LOGON`: the relay
  sends empty user names, and either of those would log every caller in
  without a password.
- All modem callers reach Synchronet from `127.0.0.1` and share one
  failed-login counter. If mistyped passwords ever trigger the temporary ban,
  raise `LoginAttemptTempBanThreshold`.

Test the RLogin ports directly: `tools/bbs-rlogin-probe.py 2300` should show
the ANSI login screen, `2340` the PETSCII one, both without any 0xFF/IAC
bytes.

## 3. The relay

`app_softmodem` passes raw bytes; Synchronet has no raw listener, and telnet
would double every 0xFF. The relay speaks RLogin upstream (byte-transparent in
Synchronet) and raw bytes downstream, one instance per terminal mode, listening
on the upstream port plus one.

```sh
install -m 755 relay/sbbs-relay.py /usr/local/bin/
install -m 644 config/default/sbbs-relay-ansi config/default/sbbs-relay-petscii /etc/default/
install -m 644 config/systemd/sbbs-relay@.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sbbs-relay@ansi sbbs-relay@petscii
```

Test: `tools/bbs-relay-probe.py 2301` connects as `Softmodem()` will and
should show a clean login banner, no leading NUL, no IAC bytes.
`tools/bbs-ansi-probe.py 2301` answers the ANSI detection and checks that
CP437 0xFF arrives unchanged.

## 4. Asterisk with the softmodem

Asterisk is built from source, because `app_softmodem` is an in-tree module.
Use Asterisk 22 and the module and spandsp patch from
[app_softmodem_v42](https://github.com/Sleazeappeal/app_softmodem_v42); its
README has the details.

1. **Patched spandsp.** Debian 13 ships spandsp 0.0.6+dfsg-2.2. Install
   `libspandsp-dev`, then build the patched library as described in
   app_softmodem_v42 and replace `/usr/lib/x86_64-linux-gnu/libspandsp.so.2.0.0`
   with it (keep the original; a `libspandsp2` package upgrade will undo the
   replacement, so hold the package or re-deploy after upgrades). Never keep a
   backup copy with the same soname inside a directory `ldconfig` scans.
2. **Build dependencies** (instead of `install_prereq`, which pulls in about
   40 unrelated packages): `bison flex libedit-dev libjansson-dev libxml2-dev
   libsqlite3-dev libssl-dev uuid-dev libspandsp-dev xmlstarlet
   libcurl4-openssl-dev libsrtp2-dev libxslt1-dev`.
3. **Build.** Copy `app_softmodem.c` from app_softmodem_v42 into `apps/`,
   `./configure --prefix=/usr/local`, and build with the **patched spandsp
   headers** first on the include path (see app_softmodem_v42):
   `make ASTCFLAGS="-I/path/to/spandsp-0.0.6+dfsg/src"`, then `make install`.
4. **User and configuration.** Create a system user `asterisk`, copy
   `config/asterisk/*` to `/usr/local/etc/asterisk/`, and make
   `pjsip.conf` from `pjsip.conf.example`: replace `pbx.example.lan` and the
   `PASSWORD-HERE` secrets (mode 0640, owner `asterisk`).
5. **Service.** Install `config/systemd/asterisk.service` and enable it. It
   runs Asterisk unprivileged with `CPUSchedulingPolicy=rr`: the softmodem
   works on fixed audio frames, and a late frame under normal scheduling
   corrupts data for callers without error correction.

Several modules log "declined to load" at start-up because of the small
dependency set; that is noise, not a fault. Note that `pjsip reload` does not
create objects that were added to `pjsip.conf` for the first time: restart
Asterisk after adding a line.

### The dialplan

`config/asterisk/extensions.conf` has one context per terminal mode:

```
[line-ansi]       ; 401-403
 ... Softmodem(127.0.0.1,2301,v(V22bis)ld(8)s(1)cbt(-16))
[line-petscii]    ; 404
 ... Softmodem(127.0.0.1,2341,v(V22)ld(8)s(1)t(-16))
```

- `c` / `b`: V.42 error correction and V.42bis compression. Modems without
  them fall back to plain async data automatically.
- `t(-16)`: transmit level. The module default of -28 dBm was too weak for at
  least one softmodem behind an ATA.
- The PETSCII line runs V.22 at 1200 bit/s without `c`. A Bell 212A-only
  modem (US C64 modems) would need `v(Bell103)` at 300 bit/s instead.

## 5. The PBX (FreePBX)

One extension per line, each with a single concurrent call. On every BBS
extension (Applications → Extensions → Advanced):

| Setting | Value | Why |
|---|---|---|
| Codecs | **ulaw only** | Any compressed codec destroys the modem signal |
| **Direct Media** | **No** | With it on, the PBX moves the media path with a re-INVITE around answer time. Calls then often failed during the V.42 setup (the link came up after 19 s, or not at all) |
| Call Recording | Never | Keeps extra processing out of the media path |
| Music on Hold | none | No transcoding path |
| Max concurrent calls | 1 | One line, one call |

Fax detection lives on inbound routes and trunks, not on extensions, and
internal extension-to-extension calls do not pass through either. If
something misbehaves, `asterisk -rx "pjsip show endpoint 401"` on the PBX shows
what is really in effect; compare it with a working extension.

## 6. The callers' ATAs

Settings on the FXS port the modem is plugged into (names from a Grandstream
HT802; other ATAs have equivalents):

- all vocoders **PCMU** only, **silence suppression (VAD) off**;
- **line echo canceller off**, **fixed, low jitter buffer**;
- fax mode **pass-through**, **no re-INVITE on fax tone**;
- call waiting off;
- **"Enable Current Disconnect"** on: the ATA drops loop current when the BBS
  hangs up. Modems that ignore loss of carrier without error correction then
  still hang up.
- Voicemail / message waiting off for that extension (on a Cisco SPA112,
  `VMWI Serv` off): a pending MWI on the line cut the incoming audio a few
  seconds into every call.

On the modem, the factory profile (`AT&F`) with V.42 and V.42bis enabled is
the best start. Dial the extension number: `ATDT401`.

## 7. First call

- `asterisk -rx "pjsip show registrations"`: all lines `Registered`.
- Dial 401 from a modem. Expect `CONNECT` at 2400 with LAP-M (and V.42bis if
  the modem reports compression), then the Synchronet banner.
- In the Asterisk log: `V.42 error correction active`, `V.42bis compression
  active`, and at the end `V.42 link released`.

## 8. Operations

- **Log rotation:** `config/logrotate/asterisk` → `/etc/logrotate.d/asterisk`.
- **Backup:** `scripts/bbs-backup.sh` → `/usr/local/sbin/`, plus
  `config/systemd/bbs-backup.service` and `.timer`. Nightly at 04:00, stops
  Synchronet for the few seconds the archive takes, keeps 14 archives in
  `/u00/backups`. These sit on the same disk: keep VM-level backups too.
- **Remote logging (optional):** `config/rsyslog/60-remote.conf`, and
  `ForwardToSyslog=yes` in `/etc/systemd/journald.conf.d/` for everything
  journald captures.
- **Modem trace:** `config/asterisk/logger.conf` describes how to switch the
  V.22bis / V.42 frame trace on at runtime.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| No answer tone, or the call drops a few seconds in | Codec other than ulaw somewhere; pending message waiting on the caller's ATA line |
| Connects, then the V.42 link takes ~20 s or fails; garbage in the login prompt | PBX Direct Media on (§5). The garbage itself is the terminal's late reply to Synchronet's ANSI detection |
| A softmodem caller (Windows) fails often, hardware modems are fine | Transmit level too low: use `t(-16)` |
| Garbage after the BBS hangs up, modem stays online | A caller without error correction whose modem ignores loss of carrier: enable the ATA's current disconnect |
| Everything broke after a system update | A `libspandsp2` upgrade replaced the patched library |
| A new line does not register | `pjsip reload` does not create new objects: restart Asterisk |
