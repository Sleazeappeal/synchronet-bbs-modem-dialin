#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
#
# bbs-backup.sh — application-level backup of the BBS host.
#
# Backs up the things that cannot be rebuilt:
#   /u00/sbbs/ctrl          Synchronet configuration
#   /u00/sbbs/data          user base, message bases, file base metadata
#   /usr/local/etc/asterisk PJSIP config (contains the SIP secrets)
#   /etc/systemd/system/*   the unit files for this stack
#   /etc/default/sbbs-relay-*
#   /etc/logrotate.d/asterisk
#
# Deliberately NOT backed up: /u00/sbbs/repo (a git checkout, rebuildable),
# /usr/local/src/asterisk-build (likewise), and any network-mounted file areas.
#
# Synchronet is stopped for the duration. A message base caught mid-write is
# the one thing a backup of a BBS must not contain, and at four lines a pause
# of a few seconds in the small hours costs nothing. The service is restarted
# from a trap, so it comes back even if the archive step fails.
#
# NOTE ON WHERE THIS LANDS: /u00 is a directory on the root filesystem, so
# these archives sit on the same disk as the data they protect. That guards
# against mistakes -- a bad edit, a deleted message area -- but not against
# losing the disk or the VM: keep VM-level backups (e.g. Proxmox vzdump) too,
# or copy the newest archive off the box.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/u00/backups}"
KEEP="${KEEP:-14}"
SERVICE="sbbs"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="${BACKUP_DIR}/bbs-${STAMP}.tar.gz"

log() { printf '%s %s\n' "$(date '+%F %T')" "$*"; }

sources=(
	/u00/sbbs/ctrl
	/u00/sbbs/data
	/usr/local/etc/asterisk
	/etc/systemd/system/sbbs.service
	/etc/systemd/system/asterisk.service
	/etc/systemd/system/sbbs-relay@.service
	/etc/logrotate.d/asterisk
)
# Glob separately: an unmatched glob inside the array would be stored literally.
for f in /etc/default/sbbs-relay-*; do
	[ -e "$f" ] && sources+=("$f")
done

mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"

was_active=0
if systemctl is-active --quiet "$SERVICE"; then
	was_active=1
fi

restore_service() {
	if [ "$was_active" -eq 1 ] && ! systemctl is-active --quiet "$SERVICE"; then
		log "restarting $SERVICE"
		systemctl start "$SERVICE"
	fi
}
trap restore_service EXIT

if [ "$was_active" -eq 1 ]; then
	log "stopping $SERVICE for a consistent copy"
	systemctl stop "$SERVICE"
fi

log "writing $ARCHIVE"
tar --create --gzip --file "$ARCHIVE" \
    --warning=no-file-changed \
    --absolute-names \
    "${sources[@]}"
chmod 0600 "$ARCHIVE"

# Restart before pruning, so the BBS is back up as early as possible.
restore_service
trap - EXIT

size="$(du -h "$ARCHIVE" | cut -f1)"
log "archive complete: $ARCHIVE ($size)"

# Prune by count, newest kept. Filename ordering is chronological by design.
mapfile -t old < <(ls -1 "${BACKUP_DIR}"/bbs-*.tar.gz 2>/dev/null | head -n -"${KEEP}")
if [ "${#old[@]}" -gt 0 ]; then
	log "pruning ${#old[@]} archive(s) beyond the newest ${KEEP}"
	rm -f -- "${old[@]}"
fi

log "done"
