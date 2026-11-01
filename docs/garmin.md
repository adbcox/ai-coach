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

- **Covered (verified against one real account):** activities, sleep, HRV, daily summaries, **Body Battery**
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
  Garmin's Swagger page
  ([Personal API Swagger docs](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/))
  has the authoritative endpoint list; it has not been read yet.
- **Per-activity training metrics are present** (checked on 30 recent
  activity records, 109 distinct fields; verified directly): training
  load, aerobic and anaerobic training effect with their messages, and a
  training-effect label (29 of 30 activities); cycling power metrics
  (average, max, normalized, time in zone; 20 of 30). No VO2max field
  appeared in the activity records.
- **Impact:** training readiness, training status and VO2max remain
  unavailable as far as found, so the app doesn't lose every training
  number: training load and training effect come with each activity. For
  the missing ones, derive equivalents from activities + HRV/sleep.
  `python-garminconnect` is an unofficial fallback that is **unverified**
  (how it authenticates, and whether it conflicts with the Personal API
  terms, are unknown), so don't rely on it.

## FIT file download (confirmed 2026-11-01)

The personal key can download original activity files: one recent cycling
activity returned HTTP 200 with a ZIP (~105 KB) holding one `.fit` file
(~260 KB) with a valid FIT header signature. Uses the download path from
Garmin's own client,
[garmin/connect-personal-api-python](https://github.com/garmin/connect-personal-api-python).

Limits of the test: one activity, cycling only; only the header was
checked, the contents were not parsed; older activities and runs are
untested. Earlier community reports say Garmin may strip some
undocumented fields (e.g. VO2max, recovery time) from API-delivered FIT
files; unverified.

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

## Fallback: python-garminconnect (unofficial, unverified)

[python-garminconnect](https://github.com/cyberjunky/python-garminconnect)
is a community client. Not used by this app. How it authenticates and
whether using it conflicts with Garmin's terms have not been checked, so
treat it as an unvetted option only if a metric the Personal API lacks
proves necessary.

## Observed response shapes (one real account, 452 activities, 2023-12 to 2026-11)

Taken from the app's data-shapes export. Units are as Garmin sends them.

- **Activity list item**: `distance` (m), `duration` (s), `averageSpeed` (m/s),
  `averageHR`/`maxHR`, `elevationGain`/`elevationLoss` (m),
  `activityTrainingLoad`, `aerobicTrainingEffect`/`anaerobicTrainingEffect`
  with `...Message` and `trainingEffectLabel`, `hrTimeInZone_1..5` (s),
  `powerTimeInZone_1..5`, `avgPower`/`normPower`, running dynamics
  (`averageRunningCadenceInStepsPerMinute`, `avgStrideLength` in cm,
  `avgGroundContactTime` ms, `avgVerticalOscillation` cm), `fastestSplit_1000`/
  `_1609`/`_5000`/`_10000`/`_21098` (s), `splitSummaries`, strength-training
  `summarizedExerciseSets`, `differenceBodyBattery`, intensity minutes.
  No `vO2MaxValue` field is present (confirmed).
- **Sports seen** (`activityType.typeKey`): running 159, strength_training 135,
  treadmill_running 31, hiking 31, golf 21, cycling 20, trail_running 19, plus
  skiing, walking, pilates, kayaking and others. Treadmill, trail, track and
  street running all count as "Running" in the app.
- **FIT samples**: 449 of 452 activities have per-sample data (avg ~2,200,
  max ~14,600 samples). Fill rates: heart rate 94%, distance 95%, speed 76%,
  GPS/altitude 72% (indoor and strength sessions have none), cadence 56%,
  power 49%.
- **Daily health data**: `sleep` (per day) has `sleepTimeSeconds`, stage
  seconds, `sleepScores.overall.value`, `sleepNeed`; `hrv`/`hrv_summaries` have
  `lastNightAvg`, `weeklyAvg`, `status` and `baseline.balancedLow/Upper`;
  `daily_summaries.data[]` has resting HR, Body Battery min/max/charged/drained,
  stress average and qualifier, steps, intensity minutes, respiration, SpO2;
  `body_battery` has intraday `[timestamp, value]` arrays.
- **Days without data** come back as well-formed objects full of nulls
  (booleans like `retro: false` and `deviceRemCapable: false` still present),
  so "empty" is decided per data type, not by looking at the JSON as a whole.
- **Weight** is in grams. Hydration returned nothing for this account.
- The per-day HRV endpoint only reached back to 2025-06 in this account while
  the HRV range endpoint went back to 2023-10, so long histories use the range data.
