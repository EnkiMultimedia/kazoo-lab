# Kazoo lab

A small Kazoo platform in Docker Compose: one CouchDB, one RabbitMQ, one Kamailio, one FreeSWITCH and one Kazoo node. Use it to test Kazoo OpenCore against stock Kamailio and FreeSWITCH with the 2600hz configurations, and to reproduce call flows end to end.

Everything is built from the sources pinned in `sources.env`; `PROVENANCE.md` says where each one comes from and what was changed.

## Start the lab

```sh
./scripts/lab.sh fetch       # clone the pinned config and Kazoo sources into sources/
./scripts/lab.sh build       # build FreeSWITCH, Kazoo and helper images
./scripts/lab.sh up          # start and wait until healthy
./scripts/lab.sh bootstrap   # master account, FreeSWITCH node, Kamailio as SBC
./scripts/lab.sh status
```

The first build compiles FreeSWITCH and Kazoo and takes a while.

## Run the tests

```sh
./scripts/lab.sh test --test all -v
```

## Hosts

| Service | Address | Node / port |
|---|---|---|
| CouchDB | `couchdb.kazoo.lab` 172.30.0.10 | 5984 (also on localhost) |
| RabbitMQ | `rabbitmq.kazoo.lab` 172.30.0.11 | 5672, management on localhost:15672 |
| FreeSWITCH | `freeswitch.kazoo.lab` 172.30.0.12 | `freeswitch@freeswitch.kazoo.lab`, SIP 11000 |
| Kamailio | `kamailio.kazoo.lab` 172.30.0.13 | SIP 5060 (also on localhost) |
| Kazoo | `kazoo.kazoo.lab` 172.30.0.20 | `kazoo@kazoo.kazoo.lab`, API on localhost:8000 |

## Change a component

1. Commit the change on the fork (`opencore` for mod_kazoo, `opencore-lab` for configs) and push it.
2. Update the ref in `sources.env` and the table in `PROVENANCE.md`.
3. `./scripts/lab.sh fetch && ./scripts/lab.sh build && ./scripts/lab.sh up`.

Notes:

- Node names are long names (`-name`), the 2600hz default.
- Kamailio is configured through command line defines (`-A`, `--substdef`) in `compose.yml`, so the stock image and the 2600hz files are used as they are.
- `lab.sh down` removes the volumes, including CouchDB data.

## Known gaps

- The inbound DID test fails. Adding a number needs teletype (notifications), which the Kazoo OpenCore release does not include, so number activation times out with a 500. The test also sends straight to FreeSWITCH from an address no carrier ACL lists.
- Kamailio logs a few `pv_eval_str` errors at startup for queries that use `$kzE` and `$subs` before the kazoo and presence modules are loaded; they are harmless.
