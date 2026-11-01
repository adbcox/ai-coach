# Install

Port **26219**. Why: the marathon is 26 miles 385 yards, which is
26.21875 miles; rounded to 26.219 and with the decimal point dropped, that
is 26219. It is also a valid, unprivileged port below Linux's ephemeral
range (32768+). Change the *host* side of the port mapping if you need a
different one; the container always listens on 26219.

> Status: v0.1 skeleton. It has first-run setup, login, saving your Garmin
> key (encrypted) and a Garmin sync that lists activities. No charts or
> maps yet (roadmap v0.2). GitHub Actions builds the Docker image on every
> push to `main` (first build succeeded); the author has not yet run that
> image. Tests, lint, the frontend build and a live browser run of the app
> (without Docker) pass.

## What you need

- A machine with Docker (Unraid, a NAS, a mini PC, a cloud VM).
- A **Garmin personal API key**:
  1. Sign in to Garmin Connect Web and open
     <https://connect.garmin.com/app/settings/personalApiToken>.
  2. **Create Key**, accept the terms, choose an expiration, **Create**.
  3. Copy the key immediately; it is shown only once.
  4. Garmin's documentation:
     <https://developer.garmin.com/gc-developer-program/personal/personal-api/>

You paste the key into the running app. Never put it in this repo, in a
chat, or in a build.

## Option A: build it yourself with Docker Compose (works anywhere)

```bash
git clone https://github.com/help-for-me/ai-endurance-coach.git
cd ai-endurance-coach
docker compose up -d --build
```

Open `http://<server-ip>:26219`. Data lives in `./data` next to the compose
file.

## Option B: pre-built image from GitHub Container Registry

Every push to `main` publishes `ghcr.io/help-for-me/ai-endurance-coach:slim`
([workflow](../.github/workflows/docker.yml)). New packages on GHCR are
private by default; the repo owner must make the package public (package
settings, Danger Zone, Change visibility) before others can pull it. Until
then use Option A.

```bash
docker run -d --name ai-endurance-coach --restart unless-stopped \
  -p 26219:26219 -v /path/to/appdata/ai-endurance-coach:/data \
  ghcr.io/help-for-me/ai-endurance-coach:slim
```

### Unraid (Iron or Copper)

Docker tab, **Add Container**, then:

| Field | Value |
| --- | --- |
| Name | `ai-endurance-coach` |
| Repository | `ghcr.io/help-for-me/ai-endurance-coach:slim` |
| Port | container `26219`, host `26219`, TCP |
| Path | container `/data`, host `/mnt/user/appdata/ai-endurance-coach` |
| Variable | `PUID` = `99` |
| Variable | `PGID` = `100` |

`PUID`/`PGID` (Unraid's `nobody:users`) make the app own its files on the
appdata share. Without them it runs as user 10001, which is fine on a plain
Docker host but leaves root-owned/foreign-owned files on Unraid shares.

Use **Add another Path, Port, Variable, Label or Device** for each mapping.
If the image is not public yet, use Option A from the Unraid terminal
instead. (Community walkthroughs of the Add Container screen:
[qui guide](https://upd.dev/autobrr/qui/src/branch/develop/documentation/docs/getting-started/docker.md),
[Portainer guide](https://oneuptime.com/blog/post/2026-03-20-portainer-unraid-community-apps/view);
for the current official steps see docs.unraid.net.)

## First run

1. Open `http://<server-ip>:26219`. Create the **admin account** (username,
   12+ character password). Only the first visit can do this.
2. **Settings**: paste the Garmin key, **Save and test**. A wrong or expired
   key is rejected with a message and nothing is stored.
3. **Sync now**. The first sync downloads your **entire** Garmin activity
   history (every activity back to your first, with its FIT file and
   per-second data) and walks back through your daily health data (sleep,
   HRV, Body Battery, daily summaries, heart rate, SpO2, steps, hydration,
   weight) until it runs out. This can take a long time on a large account;
   progress shows in Settings and you can leave the page. If it is
   interrupted or hits an error, press Sync again and it continues where it
   stopped. After that it only fetches what is new, every 6 hours
   (`AEC_SYNC_INTERVAL_HOURS`, `0` disables). **Re-sync all history** re-scans
   everything and fills any gaps.
4. **Activities** lists what was imported.

The activity-list response from Garmin has not been checked against a live
account in the build environment (it could not reach Garmin), so the first
real sync is the first live test. If it reports a problem, the message in
Settings says what failed.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `26219` | Listening port inside the container |
| `PUID` / `PGID` | `10001` | User/group the app runs as; the container starts as root only to fix `/data` ownership, then drops to this user. Unraid: `99` / `100` |
| `AEC_DATA_DIR` | `/data` | Data volume |
| `AEC_SECURE_COOKIES` | `false` | Set `true` when served over HTTPS |
| `AEC_APP_SECRET` / `AEC_APP_SECRET_FILE` | unset | Master key override; keeps the encryption key off the data volume (use on a cloud host) |
| `AEC_SYNC_INTERVAL_HOURS` | `6` | Background sync interval, `0` = off |

## Data and backups

Everything is on the `/data` volume:

- `db/` SQLite database (activities, per-second samples, accounts)
- `activities/garmin/` the original downloaded files (ZIP with `.fit`)
- `secrets/master.key` encrypts your saved Garmin key. Keep it **separate**
  from database backups. If you lose it you only need to paste the Garmin
  key again.

Back up `db/` and `activities/`. Garmin keys expire; when yours does, sync
reports an auth error and you paste a new key.

## Security

- Do not expose it to the internet without HTTPS (reverse proxy) and
  `AEC_SECURE_COOKIES=true`, ideally behind a VPN. It is single-user with a
  built-in login and a basic brute-force throttle, and it is
  [vibe-coded](../README.md#disclaimer-vibe-coded-use-at-your-own-risk).
