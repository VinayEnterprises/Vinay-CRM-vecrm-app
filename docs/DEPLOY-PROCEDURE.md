# VECRM Backend Deploy Procedure

This document outlines the strict deployment and rollback procedure for the VECRM Frappe v15 backend on the Contabo Mumbai VPS.

**The Golden Rule**: Every deploy must capture a git tag BEFORE pulling new code.

## Pre-deploy

Before executing any deployment, create a rollback tag on the current production HEAD and verify it.

1. Ensure your working tree is clean:
   ```bash
   git status
   ```
2. Create the rollback tag:
   ```bash
   git tag rollback/$(date +%Y-%m-%d-%H%M)
   ```
3. Verify the tag exists:
   ```bash
   git tag -l "rollback/*"
   ```
   *(Copy this output for your session notes).*

## Deploy steps

1. Pull the latest code from the remote repository:
   ```bash
   git pull origin main
   ```
2. Rebuild the Docker container (using a baked COPY image, no cache):
   ```bash
   docker compose build --no-cache vecrm-backend
   ```
3. Restart the container in the background:
   ```bash
   docker compose up -d vecrm-backend
   ```
4. Post-deploy verify (example check for a sentinel file/string):
   ```bash
   docker exec vecrm-backend-1 grep <sentinel> /path/to/file
   ```

## Rollback

If the deploy fails or introduces critical issues, immediately roll back to the previously tagged state.

1. Checkout the specific rollback tag:
   ```bash
   git checkout rollback/YYYY-MM-DD-HHmm
   ```
2. Rebuild and restart the container:
   ```bash
   docker compose build --no-cache vecrm-backend
   docker compose up -d vecrm-backend
   ```
3. Verify the rollback state matches expectations using the same grep sentinel:
   ```bash
   docker exec vecrm-backend-1 grep <sentinel> /path/to/file
   ```

## Close-doc convention

Session handovers or close-docs **MUST** include the literal CLI output proving the rollback tag was created. 

- Prose claiming "tag exists" is **NOT acceptable**.
- Provide the actual terminal output snippet in your notes:
  ```bash
  git tag -l "rollback/*" | tail -5
  ```

## Tag cleanup

Maintain a clean tag history to avoid clutter.
- Keep the last 5 rollback tags.
- Prune older tags on a quarterly basis.
