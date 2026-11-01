# Garmin Personal API

Garmin now has an **official personal-use path**: the Connect Personal
API. It gives access to your own data with a self-generated key — no
partner approval, no credential-scraping. 
- **Create your key** (logged in to Garmin Connect Web):
  <https://connect.garmin.com/app/settings/personalApiToken>
- **Garmin's documentation:**
  <https://developer.garmin.com/gc-developer-program/personal/personal-api/>
  (see also the
  [Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/))

## Setup

1. Open the key page above → **Create Key** → read and accept the Terms
   and Conditions → choose an expiration period → **Create**.
2. The key is **shown only once** — copy it immediately and store it like
   a password (environment variable or Docker secret, never in git).
3. The key can't call Connect APIs directly. Exchange it for an access
   token:

```bash
curl -X POST 'https://personal.connectapi.garmin.com/personalapitoken-service/personal-api/personal-api-key/token' \
  -H 'Authorization: ApiKey [your-api-key]'
```

   Replace `[your-api-key]` with the generated key. The sync job repeats
   this exchange whenever its access token expires.
4. Deleting the key on Garmin Connect Web invalidates it and every token
   derived from it.

## Data coverage (probed against one real account, 2026-11-01)

- **Covered:** activities, sleep, HRV, daily summaries, **Body Battery**
  (min/max/charged/drained/latest + separate intraday report) and
  **stress** (average/max + rest/low/medium/high proportions) — both
  populated on 31 of 31 recent days. Fitness age, heart-rate zones and
  SpO2 also available. The dedicated daily-stress endpoint 404s but the
  daily summaries make it redundant.
- **Not found (404):** training readiness, training status, VO2max
  (latest and daily), endurance score, devices, personal records, race
  predictions. Caveat: paths were guessed from knowledge of Garmin's
  internal API, not official docs, so this matches the community claim
  that these are missing but is **not proof** they're unreachable.
  Check the official docs page above for the authoritative endpoint list.
- Impact: the app loses Garmin's own readiness/VO2max/training-status
  numbers; derive equivalents from activities + HRV/sleep, or fall back
  to `python-garminconnect` for just those metrics if they prove needed.

## Terms — unconfirmed, read before relying on this

- Garmin frames the Personal tier as personal use of your own data; the
  FAQ doesn't mention AI tools.
- The Developer Program Agreement reportedly bars sharing the key or
  passing user data to third-party services without Garmin's written
  permission (§5.2(e), §5.2(o)); the version read didn't name the
  Personal tier, so how much applies to a personal key is unclear.
- Sources conflict on AI use: the agreement PDF read didn't mention AI;
  a secondary source says §15.10 allows AI processing with disclosure and
  explicit user consent. The PDF may be an older version.
- **None of this was read from raw clause text** (summaries via WebFetch
  only), and the Personal tier's own terms (shown at key creation) were
  not read. Treat as unconfirmed; read the actual terms at key creation.
- Working reading: a local coach on your own data, staying on the
  user's own server, doesn't look like third-party disclosure. A
  **hosted-model fallback would likely count as a third party** — prefer a local agent. Not legal advice.

## Maintenance

- The key **expires** (you pick the period at creation). Track the expiry
  date and add a reminder a few weeks ahead (planned: in-app warning).

## Fallback: python-garminconnect (unofficial)

[python-garminconnect](https://github.com/cyberjunky/python-garminconnect)
logs in with your own credentials. Actively maintained (adapted to a
March 2026 auth change via `curl_cffi`), but it's unauthorized automated
access in a generic ToS sense and breaks when Garmin changes auth. Use
only for metrics the Personal API lacks.

