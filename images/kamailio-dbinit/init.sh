#!/bin/sh
# Build /var/lib/kamailio/kazoo.db with the kazoo-configs-kamailio schema
# scripts (mounted at /etc/kamailio/db_scripts), unless it already exists.
set -e

DB_DIR=/var/lib/kamailio
if [ -s "$DB_DIR/kazoo.db" ]; then
    echo "kamailio database present"
    exit 0
fi

DB_ENGINE=db_sqlite DB_KAZOO_LOCATION="$DB_DIR" RESULTED_SQL=/tmp/kazoodb.sql \
    sh /etc/kamailio/db_scripts/create-kazoodb-sql.sh
echo "kamailio database created"
