# vecrm/maintenance.py
#
# Permanent maintenance/health surface for the VECRM app.
#
# seed_probe(): L10 reachability probe. Confirms Frappe-context maintenance
# functions in this app are invocable via the proven harness
# `bench --site <site> execute vecrm.maintenance.<fn>`. Side-effect-free:
# performs no DB read or write. Durable health check intended to survive
# image rebuilds and container --force-recreate (the gap S8 closes).


def seed_probe():
    print("VECRM_MAINTENANCE_PROBE_OK vecrm.maintenance reachable via bench execute")
