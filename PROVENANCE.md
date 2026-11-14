# Provenance

Every component of the lab, where it comes from, and what we changed. The lab is built clean room: only public upstream sources, our public forks of them, and Kazoo OpenCore are used. Nothing is taken from other private forks.

Pinned commits are in `sources.env`; this page explains them.

## Components

| Component | Source | Pinned | Our changes |
|---|---|---|---|
| FreeSWITCH | [signalwire/freeswitch](https://github.com/signalwire/freeswitch) | `v1.11.3` | None |
| sofia-sip | [freeswitch/sofia-sip](https://github.com/freeswitch/sofia-sip) | `v1.13.19` | None |
| spandsp | [freeswitch/spandsp](https://github.com/freeswitch/spandsp) | `8f1e1646` | None |
| mod_kazoo | [EnkiMultimedia/mod_kazoo](https://github.com/EnkiMultimedia/mod_kazoo) branch `opencore`, fork of [freeswitch/mod_kazoo](https://github.com/freeswitch/mod_kazoo) `0878e13e` | `fc2430be` | Fixes listed below |
| FreeSWITCH config | [EnkiMultimedia/kazoo-configs-freeswitch](https://github.com/EnkiMultimedia/kazoo-configs-freeswitch) branch `opencore-lab`, from 2600hz `4.3` (`ce2ec4b3`) | `053c8c67` | Node settings from the environment; modules the image lacks commented out |
| Kamailio | `ghcr.io/kamailio/kamailio-ci:6.1` (upstream image) | 6.1.5 | None |
| Kamailio config | [EnkiMultimedia/kazoo-configs-kamailio](https://github.com/EnkiMultimedia/kazoo-configs-kamailio) branch `opencore-lab`, from 2600hz `4.3` (`63cece75`) | `b9e917c6` | Ported to Kamailio 6.1 and the stock modules, see below |
| Kazoo config | [EnkiMultimedia/kazoo-configs-core](https://github.com/EnkiMultimedia/kazoo-configs-core) `4.3` | `cbcc916d` | None in the fork; `config/kazoo/config.ini` is derived from its `config.ini` with lab hosts and ports |
| Kazoo | [EnkiMultimedia/kazoo-opencore](https://github.com/EnkiMultimedia/kazoo-opencore) branch `otp29-stock-stack` | `c48d9068` | That branch |
| CouchDB | `couchdb:3.5` | | None |
| RabbitMQ | `rabbitmq:4.1-management` | | Consistent hash exchange plugin enabled |
| Kamailio DB init | `alpine:3.22` + `sqlite`, schema files from the Kamailio image | | Runs the config's own schema scripts |

## mod_kazoo changes

Each change is one commit on the `opencore` branch, written from the upstream mod_kazoo, FreeSWITCH and erl_interface sources. The commit messages give the reasoning.

| Commit | Change |
|---|---|
| `dea988e` | Do not free a fetch reply handed to the fetch thread (use-after-free and double free on every fetch) |
| `1a91b6d` | Echo the call tag as an opaque term (OTP 24+ `gen_server:call` and `net_adm:ping`) |
| `6406a25` | Mark the definitions object as not needing an executable stack (glibc 2.41) |
| `c69eb37` | Always call `ei_init()` |
| `00d7881` | Leave room for the NUL in bounded string decoding |
| `dad454b` | Do not write a json_api reply for a cast |
| `14af544` | Count bgapi jobs and receive handlers before starting their threads |
| `e70dd13` | Read the cookie file and host name safely |
| `5b0f7e5` | NUL-terminate node names and pass ei a real address |
| `5173e5d` | Keep `$${}` expansion inside its buffer |
| `5bd635f` | Release the agent lock when the fetch event cannot be created |
| `f5e2659` | Answer badarg to a commands request without a list |
| `fc2430b` | FreeSWITCH 1.11 and OTP 29 notes, known issues, build check |

Issues found and not fixed yet are in the fork's `doc/known-issues.md`.

## Kamailio config changes

Each change is one commit on the `opencore-lab` branch of `EnkiMultimedia/kazoo-configs-kamailio`, made against the stock `kamailio-ci:6.1` image.

| Commit | Change |
|---|---|
| `b5337f8` | Add the dispatcher role for Kamailio 6.1 (copy of the 5.5 role) |
| `56756f7` | Fix the MWI presence body define for Kamailio 6 |
| `0aae655` | Support the stock `db_sqlite` module (same schema and queries as `db_kazoo`) |
| `fe09135` | Do not bind the acc API for `uac_redirect` without the accounting role |
| `fc789fb` | Count affected rows without `DB_CAP_AFFECTED_ROWS` (SQLite `changes()`) |
| `a41285f` | Read listener details with Kamailio 6 key names (node advertisements) |
| `b9e917c` | Do not check AMQP availability with the upstream kazoo module |

## FreeSWITCH config changes

| Commit | Change |
|---|---|
| `8899a8a` | Configure the kazoo node (cookie, node name) from the environment |
| `053c8c6` | Skip modules the lab image does not build |

