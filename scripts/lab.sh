#!/bin/sh
# Kazoo lab driver.
#
#   lab.sh fetch       clone the pinned sources into sources/
#   lab.sh build       build the images
#   lab.sh up          start the stack and wait until it is healthy
#   lab.sh bootstrap   master account, FreeSWITCH node, Kamailio ACL
#   lab.sh test [...]  run the SIPp tests (arguments go to the runner)
#   lab.sh status      node and connection status
#   lab.sh logs [svc]  follow logs
#   lab.sh down        stop the stack and remove its volumes
set -eu

cd "$(dirname "$0")/.."
. ./sources.env

COMPOSE="docker compose --env-file sources.env"
COOKIE=kazoo_lab_cookie
KAZOO_NODE=kazoo@kazoo.kazoo.lab
FS_NODE=freeswitch@freeswitch.kazoo.lab
KAMAILIO_IP=172.30.0.13

log() { echo "[lab] $*"; }

checkout() { # repo ref dir
    if [ ! -d "$3/.git" ]; then
        git clone -q "$1" "$3"
    fi
    git -C "$3" remote set-url origin "$1"
    git -C "$3" fetch -q origin
    git -C "$3" checkout -q "$2"
    log "$(basename "$3") at $(git -C "$3" rev-parse --short HEAD)"
}

wait_healthy() { # service timeout
    t=0
    while :; do
        s=$(docker inspect -f '{{.State.Health.Status}}' "kazoo-lab-$1-1" 2>/dev/null || echo missing)
        [ "$s" = healthy ] && return 0
        [ "$t" -ge "$2" ] && { log "$1 is $s"; return 1; }
        sleep 5; t=$((t + 5))
    done
}

case "${1:-}" in
    fetch)
        mkdir -p sources
        checkout "$KAMAILIO_CONFIGS_REPO" "$KAMAILIO_CONFIGS_REF" sources/kazoo-configs-kamailio
        checkout "$CORE_CONFIGS_REPO" "$CORE_CONFIGS_REF" sources/kazoo-configs-core
        checkout "$KAZOO_REPO" "$KAZOO_REF" sources/kazoo-opencore
        ;;
    build)
        $COMPOSE build
        $COMPOSE --profile test build sipp
        ;;
    up)
        $COMPOSE up -d
        for s in couchdb rabbitmq freeswitch kazoo; do
            log "waiting for $s"; wait_healthy "$s" 600
        done
        ;;
    bootstrap)
        log "master account"
        docker exec kazoo-lab-kazoo-1 /opt/kazoo/bin/sup -n kazoo -c "$COOKIE" \
            crossbar_maintenance create_account admin master.kazoo.lab admin admin123 || true
        log "allowing Kamailio ($KAMAILIO_IP) as SBC"
        docker exec kazoo-lab-kazoo-1 /opt/kazoo/bin/sup -n kazoo -c "$COOKIE" \
            ecallmgr_maintenance allow_sbc kamailio "$KAMAILIO_IP" || true
        log "adding $FS_NODE"
        docker exec kazoo-lab-kazoo-1 /opt/kazoo/bin/sup -n kazoo -c "$COOKIE" \
            ecallmgr_maintenance add_fs_node "$FS_NODE" || true
        ;;
    test)
        shift
        $COMPOSE --profile test run --rm sipp "$@"
        ;;
    status)
        docker exec kazoo-lab-kazoo-1 /opt/kazoo/bin/sup -n kazoo -c "$COOKIE" ecallmgr_maintenance node_summary || true
        docker exec kazoo-lab-freeswitch-1 fs_cli -x "erlang status" || true
        docker exec kazoo-lab-kamailio-1 kamcmd dispatcher.list 2>/dev/null | grep -E "URI|FLAGS" || true
        for s in couchdb rabbitmq kamailio freeswitch kazoo; do
            printf '%s restarts=%s\n' "$s" "$(docker inspect -f '{{.RestartCount}}' "kazoo-lab-$s-1" 2>/dev/null)"
        done
        ;;
    logs)
        shift; $COMPOSE logs -f "$@"
        ;;
    down)
        $COMPOSE --profile test down -v
        ;;
    *)
        sed -n '2,12p' "$0"; exit 2
        ;;
esac
