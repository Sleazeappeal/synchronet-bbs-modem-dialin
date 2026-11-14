#!/bin/bash
# Part of the 40-column PETSCII screens, GPL-2.0-or-later (see NOTICE.txt).
# Installs the 40-column (C64/PETSCII) screens for Synchronet.
# 80-column callers are not affected: Synchronet only picks *.40col.*
# menus for 40-column terminals, and mods/logon.js only changes text
# strings when the terminal is narrower than 80 columns.
#
# Run on the BBS host from this folder:
#   sudo ./install.sh [--force] [SBBS_DIR]      (default /u00/sbbs)
# Without --force nothing is overwritten: a target that exists with
# other content stops the install before anything is written. With
# --force such files are first copied to <file>.bak-<timestamp>.
set -euo pipefail

FORCE=0
if [ "${1:-}" = "--force" ]; then FORCE=1; shift; fi
SBBS=${1:-/u00/sbbs}
SRC=$(cd "$(dirname "$0")" && pwd)
STAMP=$(date +%Y%m%d-%H%M%S)
# mods/logonlist.js is a patched copy of this exec/logonlist.js
LOGONLIST_STOCK_MD5=28f50a11fb0b5caed41b8525ef2c14e0

die() { echo "ERROR: $*" >&2; exit 1; }

MAIN_INI=$SBBS/ctrl/main.ini
[ -f "$MAIN_INI" ] || die "$MAIN_INI not found (wrong SBBS_DIR?)"
# Owner of the BBS data (main.ini may be root-owned after SCFG runs as root)
[ -d "$SBBS/text" ] || die "$SBBS/text not found"
OWNER=$(stat -c %U:%G "$SBBS/text")

# The mods dir from main.ini, relative to ctrl/ when not absolute
MODS=$(sed -n 's/^[[:space:]]*mods[[:space:]]*=[[:space:]]*//p' "$MAIN_INI" | head -n 1)
[ -n "$MODS" ] || die "no 'mods=' directory set in $MAIN_INI"
case $MODS in /*) ;; *) MODS=$SBBS/ctrl/$MODS ;; esac
MODS=$(realpath -m "$MODS")

STOCK=$(md5sum "$SBBS/exec/logonlist.js" | cut -d' ' -f1)
[ "$STOCK" = "$LOGONLIST_STOCK_MD5" ] ||
	die "exec/logonlist.js differs from the version mods/logonlist.js was made from; re-create the patch for this Synchronet version"

# source (relative to this folder) -> target
FILES=(
	"text/answer.40col.msg:$SBBS/text/answer.40col.msg"
	"mods/logon.js:$MODS/logon.js"
	"mods/logonlist.js:$MODS/logonlist.js"
	"mods/text/system.40col.msg:$MODS/text/system.40col.msg"
)
for f in "$SRC"/mods/text/menu/*; do
	FILES+=("mods/text/menu/$(basename "$f"):$MODS/text/menu/$(basename "$f")")
done

# Pre-flight: find conflicts before writing anything
CONFLICT=0
for e in "${FILES[@]}"; do
	src=$SRC/${e%%:*}; dst=${e#*:}
	if [ -e "$dst" ] && ! cmp -s "$src" "$dst"; then
		echo "exists with other content: $dst"
		CONFLICT=1
	fi
done
if [ $CONFLICT = 1 ] && [ $FORCE = 0 ]; then
	die "nothing installed; check the files above, then re-run with --force (backs them up)"
fi

# Only directories this script creates get the owner and mode; an
# existing mods/ keeps its own (it is 0700 on some installs).
for d in "$MODS" "$MODS/text" "$MODS/text/menu"; do
	[ -d "$d" ] || install -d -o "${OWNER%:*}" -g "${OWNER#*:}" -m 755 "$d"
done
for e in "${FILES[@]}"; do
	src=$SRC/${e%%:*}; dst=${e#*:}
	if [ -e "$dst" ]; then
		if cmp -s "$src" "$dst"; then echo "same:      $dst"; continue; fi
		cp -p "$dst" "$dst.bak-$STAMP"
		echo "backed up: $dst.bak-$STAMP"
	fi
	install -o "${OWNER%:*}" -g "${OWNER#*:}" -m 664 "$src" "$dst"
	echo "installed: $dst"
done
echo "Done. New logons use the files; no restart needed."
