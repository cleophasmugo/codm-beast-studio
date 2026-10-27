#!/bin/sh
# Starts as root only long enough to make the data dir writable (hosted disks such as Render's
# mount root-owned), then drops to the unprivileged beast user.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p "${BEAST_DATA_DIR:-/data}"
  chown beast:beast "${BEAST_DATA_DIR:-/data}"
  exec setpriv --reuid=beast --regid=beast --init-groups "$@"
fi
exec "$@"
