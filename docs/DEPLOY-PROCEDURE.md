## VECRM Backend Deploy Procedure

### Pre-deploy
No rollback tags needed — SCP deploys are file-level, rollback is
re-SCP of the previous file version.

### Deploy steps (from your MacBook)
1. SCP the changed file(s) to VPS tmp:
   scp vecrm/api.py vemio:/tmp/api.py

2. Docker cp into the container:
   ssh vemio "docker cp /tmp/api.py vecrm-backend-1:/home/frappe/frappe-bench/apps/vecrm/vecrm/api.py"

3. Restart the container:
   ssh vemio "docker restart vecrm-backend-1"
   sleep 20

4. Verify container is Up:
   ssh vemio "docker ps --filter name=vecrm-backend-1 --format '{{.Status}}'"

5. Verify the change landed:
   ssh vemio "docker exec vecrm-backend-1 grep '<sentinel>' /home/frappe/frappe-bench/apps/vecrm/vecrm/api.py"

### hooks.py deploys (additional step)
If hooks.py was changed (new scheduler_events), you MUST also:
   ssh vemio "docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in clear-cache"
   ssh vemio "docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in execute frappe.core.doctype.scheduled_job_type.scheduled_job_type.sync_jobs"
Container restart alone does NOT register new cron jobs.

### Doctype JSON deploys (additional step)
If doctype JSONs changed:
   scp the JSON to /tmp, docker cp into the container, then:
   ssh vemio "docker exec vecrm-backend-1 bench --site crm.vinayenterprises.co.in reload-doctype 'VECRM Travel Voucher'"

### Portal deploys
Portal (vecrm-portal) auto-deploys via Vercel on merge to main.
No manual steps needed.

### Close-doc convention
Session handover must include the grep verification output proving
the deployed file contains the expected change.
