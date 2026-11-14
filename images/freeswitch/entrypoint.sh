#!/bin/sh
# mod_kazoo registers its node name with epmd, which FreeSWITCH does not start.
set -e
epmd -daemon
exec freeswitch "$@"
