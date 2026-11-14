# Creates the Kamailio SQLite database for kazoo-configs-kamailio, once.
# Kamailio itself runs the stock kamailio-ci image; this image only adds the
# sqlite3 tool next to the schema files shipped in that image.
ARG KAMAILIO_IMAGE=ghcr.io/kamailio/kamailio-ci:6.1
FROM ${KAMAILIO_IMAGE} AS kamailio

FROM alpine:3.22
RUN apk add --no-cache sqlite
COPY --from=kamailio /usr/share/kamailio/db_sqlite /usr/share/kamailio/db_sqlite
COPY init.sh /init.sh
ENTRYPOINT ["/bin/sh", "/init.sh"]
