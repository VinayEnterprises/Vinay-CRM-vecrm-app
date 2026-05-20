# Canonical MariaDB probe pattern (vecrm-db-1)

**Purpose:** Read-only SQL probes against the vecrm site DB from the operator's shell.
**Site DB name:** `_02c50791cf17d9de` (crm.vinayenterprises.co.in)
**Container:** `vecrm-db-1` (MariaDB 11.8)
**Compose source:** `/opt/vecrm/compose.yaml` + `/opt/vecrm/overrides/compose.mariadb.yaml`

## Where the credential comes from

The active compose chain uses `compose.mariadb.yaml` (NOT `compose.mariadb-secrets.yaml`). The MariaDB root password is set via environment variable inside the container:

- Host `.env` defines `DB_PASSWORD=<actual-password>`
- `compose.mariadb.yaml` maps `MYSQL_ROOT_PASSWORD: ${DB_PASSWORD:-123}` into the container
- Container has `MYSQL_ROOT_PASSWORD=<value>` in its env at runtime

**There is no `/run/secrets/` directory in vecrm-db-1.** Patterns that reference `/run/secrets/db_root_password` will silently fall through to password-less auth and produce `ERROR 1045 (28000): Access denied`. The original S20 session scripts had a correct fallback to `$MYSQL_ROOT_PASSWORD`; only the S20-close-handover §3 distillation dropped it.

## Canonical one-line probe

For any read-only SELECT against the vecrm site DB:

```bash
ssh root@217.216.58.117 "printf '%s\n' \"<SQL>\" | docker exec -i vecrm-db-1 bash -lc 'mariadb -uroot -p\"\$MYSQL_ROOT_PASSWORD\" _02c50791cf17d9de'"
```

Where `<SQL>` is a single SQL statement terminated with a semicolon. Backticks around MariaDB table names with special characters (e.g. `tabVECRM Voucher Counter`) must be doubly escaped inside the SSH-then-bash-then-mariadb quoting chain.

## Worked example — read voucher counter values

```bash
ssh root@217.216.58.117 "printf '%s\n' \"SELECT name, last_value FROM \\\`tabVECRM Voucher Counter\\\` WHERE name IN ('LEAD-26-27','INQ-26-27');\" | docker exec -i vecrm-db-1 bash -lc 'mariadb -uroot -p\"\$MYSQL_ROOT_PASSWORD\" _02c50791cf17d9de'"
```

Expected output if counters are unused:
```
name		last_value
LEAD-26-27	0
INQ-26-27	0
```

## Alternative: interactive shell on the container

For ad-hoc multi-statement work, drop into an interactive mariadb session:

```bash
ssh root@217.216.58.117
docker exec -it vecrm-db-1 bash
mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" _02c50791cf17d9de
```

The non-interactive stdin-pipe pattern (preferred for scripts) wedges on multi-line interactive paste; the interactive pattern handles multi-statement input naturally.

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `ERROR 1045 (28000): Access denied for user 'root'@'localhost' (using password: NO)` | `MYSQL_ROOT_PASSWORD` resolves empty (wrong env-var name, wrong container, wrong quoting) | Verify with `docker exec vecrm-db-1 bash -c 'echo "len=${#MYSQL_ROOT_PASSWORD}"'` |
| `Enter password:` prompt blocks | Missing `-p"$VAR"` (note no space between `-p` and the password) | Add `-p"$MYSQL_ROOT_PASSWORD"` |
| `ERROR 1146 (42S02): Table '...' doesn't exist` | Wrong DB name; check `_02c50791cf17d9de` against `bench --site <site> mariadb` if the site DB has changed | Re-derive site DB hash from `frappe.conf.db_name` |
| Output wedges mid-query | Used interactive `mariadb` with multi-line stdin paste | Switch to `-e "$SQL"` flag or non-interactive `printf | docker exec -i` |

## Reversal conditions

If the compose chain is changed to use `compose.mariadb-secrets.yaml` (Docker secrets pattern), the probe pattern must be re-derived. The `compose.mariadb-secrets.yaml` file exists in `/opt/vecrm/overrides/` but is NOT in the active chain. Migration to Docker secrets would be triggered by a security-hardening pass and would require explicit re-documentation here.

## Provenance

- Compose recon: S21 PD-S20-DOCS-DRIFT closure recon, 2026-05-20
- Container env verified: `docker inspect vecrm-db-1 --format '{{range .Config.Env}}{{println .}}{{end}}'` showed `MYSQL_ROOT_PASSWORD` set, no `/run/secrets/` mount
- Closes pendency: PD-S21-DBPROBE
- Authority: this document is canonical over any prior handover §3 "DB interaction discipline" prose
