# FreeSWITCH for the Kazoo lab.
#
# FreeSWITCH, sofia-sip and spandsp: upstream sources, unmodified.
# mod_kazoo: EnkiMultimedia/mod_kazoo (fork of freeswitch/mod_kazoo).
# Configuration: EnkiMultimedia/kazoo-configs-freeswitch (fork of 2600hz).
# All refs come from sources.env through build arguments.

ARG ERLANG_VERSION=29

FROM erlang:${ERLANG_VERSION} AS builder

ARG FREESWITCH_REPO
ARG FREESWITCH_REF
ARG SOFIA_SIP_REPO
ARG SOFIA_SIP_REF
ARG SPANDSP_REPO
ARG SPANDSP_REF
ARG MOD_KAZOO_REPO
ARG MOD_KAZOO_REF
ARG FREESWITCH_CONFIGS_REPO
ARG FREESWITCH_CONFIGS_REF

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates build-essential cmake automake autoconf \
        libtool libtool-bin pkg-config yasm binutils \
        libssl-dev libedit-dev libsqlite3-dev libcurl4-openssl-dev \
        libpcre2-dev libspeex-dev libspeexdsp-dev libtiff-dev libjpeg-dev \
        libsndfile1-dev libldns-dev libopus-dev uuid-dev \
        libshout3-dev libmpg123-dev libmp3lame-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src
ENV PKG_CONFIG_PATH=/usr/local/freeswitch/lib/pkgconfig:/usr/local/lib/pkgconfig

# checkout REPO REF DIR: clone and pin a commit, tag or branch
RUN printf '#!/bin/sh\nset -e\ngit clone -q "$1" "$3"\ncd "$3"\ngit checkout -q "$2"\ngit log -1 --format="%%H %%s"\n' > /usr/local/bin/checkout \
    && chmod +x /usr/local/bin/checkout

RUN checkout "${SOFIA_SIP_REPO}" "${SOFIA_SIP_REF}" sofia-sip \
    && cd sofia-sip && ./bootstrap.sh && ./configure && make -j"$(nproc)" && make install && ldconfig

RUN checkout "${SPANDSP_REPO}" "${SPANDSP_REF}" spandsp \
    && cd spandsp && ./bootstrap.sh && ./configure && make -j"$(nproc)" && make install && ldconfig

RUN checkout "${FREESWITCH_REPO}" "${FREESWITCH_REF}" freeswitch

WORKDIR /usr/src/freeswitch

# The modules loaded by kazoo-configs-freeswitch (4.3), minus those needing
# libraries the image does not ship (av, siren, amr, ilbc, flite).
RUN printf '%s\n' \
        applications/mod_commands applications/mod_conference applications/mod_db \
        applications/mod_dptools applications/mod_expr applications/mod_hash \
        applications/mod_http_cache applications/mod_spandsp \
        codecs/mod_g723_1 codecs/mod_opus \
        dialplans/mod_dialplan_xml \
        endpoints/mod_loopback endpoints/mod_sofia \
        event_handlers/mod_event_socket \
        formats/mod_local_stream formats/mod_native_file formats/mod_shout \
        formats/mod_sndfile formats/mod_tone_stream \
        loggers/mod_console loggers/mod_logfile loggers/mod_syslog \
        say/mod_say_en \
        > modules.conf \
    && ./bootstrap.sh -j \
    && ./configure --prefix=/usr/local/freeswitch --disable-debug \
        --disable-libyuv --disable-libvpx --with-openssl \
    && make -j"$(nproc)" && make install

RUN checkout "${MOD_KAZOO_REPO}" "${MOD_KAZOO_REF}" /usr/src/mod_kazoo \
    && cd /usr/src/mod_kazoo && ./bootstrap.sh && ./configure \
    && make -j"$(nproc)" && make install \
    && so=/usr/local/freeswitch/lib/freeswitch/mod/mod_kazoo.so \
    && readelf -lW "$so" | grep GNU_STACK \
    && ! readelf -lW "$so" | grep GNU_STACK | grep -q E

RUN checkout "${FREESWITCH_CONFIGS_REPO}" "${FREESWITCH_CONFIGS_REF}" /usr/src/kazoo-configs-freeswitch

FROM erlang:${ERLANG_VERSION}-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates procps \
        libssl3t64 libedit2 libsqlite3-0 libcurl4t64 libpcre2-8-0 \
        libspeex1 libspeexdsp1 libtiff6 libjpeg62-turbo libsndfile1 \
        libldns3t64 libopus0 libuuid1 libshout3 libmpg123-0t64 libmp3lame0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/libsofia-sip-ua.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/libspandsp.so* /usr/local/lib/
COPY --from=builder /usr/local/freeswitch /usr/local/freeswitch

RUN ldconfig \
    && missing=$(ldd /usr/local/freeswitch/bin/freeswitch /usr/local/freeswitch/lib/freeswitch/mod/*.so | grep 'not found' || true) \
    && if [ -n "$missing" ]; then echo "$missing"; exit 1; fi

ENV PATH=/usr/local/freeswitch/bin:${PATH} \
    FS_CONFIG_DIR=/usr/local/freeswitch/etc/freeswitch

# kazoo-configs-freeswitch is the whole configuration
RUN rm -rf ${FS_CONFIG_DIR} && mkdir -p ${FS_CONFIG_DIR}
COPY --from=builder /usr/src/kazoo-configs-freeswitch/freeswitch/ ${FS_CONFIG_DIR}/

COPY entrypoint.sh /entrypoint.sh

# KAZOO_COOKIE and KAZOO_NODENAME are read by the config (env-set)
ENV KAZOO_COOKIE=change_me \
    KAZOO_NODENAME=freeswitch

EXPOSE 11000/udp 11000/tcp 8021/tcp 8031/tcp

HEALTHCHECK --interval=10s --timeout=10s --start-period=30s --retries=6 \
    CMD fs_cli -x status | grep -q UP || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["-nonat", "-nf"]
