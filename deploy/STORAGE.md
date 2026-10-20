# EditorGPT VPS storage

EditorGPT's repository lives at `/opt/rafieigroup/editor-app` on the attached
100 GB disk. `/opt/ai-render` remains a compatibility symlink for deployment
commands and Caddy's static root. Compose project identity is fixed as `ai-render`.

Persistent data lives below `/opt/rafieigroup/editor-storage/volumes/`:
`job_data`, `pg_data`, `redis_data`, `frontend_dist`. Bind mounts preserve the
original `/var/lib/docker/volumes/ai-render_<name>/_data` paths. They are recorded
in the host's `/etc/fstab` with a dependency on `/opt/rafieigroup`.

The server Compose overlay mounts per-service `/tmp` and `/root/.cache` below
`editor-storage/tmp` and `editor-storage/cache`, preventing render scratch data
from filling the root filesystem. Do not delete stopped containers or volumes.

Before moving data: stop only this Compose project's services, verify their
stopped state, preserve ownership, move files, install mounts, validate Compose,
then restart and verify PostgreSQL, Redis writes, API health and existing jobs.
Do not copy a live PostgreSQL data directory as a migration substitute.

Docker/containerd image storage is host-wide and remains separate. Moving it
would affect unrelated applications and requires a separate maintenance plan.
This migration does not relocate other services or format any disk.
