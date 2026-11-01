# Changelog

## 0.2.0

New
- **Recovery page**: sleep score and duration (deep/REM), HRV with your balanced
  range, resting heart rate, Body Battery and stress, 30 days to 1 year.
- **Weekly mileage chart** on the dashboard: rolling 7-day total in km per week
  (was km per day), next to the rolling 7-day longest run.
- Dashboard opens on **Running** (remembered); new **Hiking** group; treadmill,
  trail and track runs count as running.
- **Activities list** loads 100 at a time with "Show more" and sport filters.
- Run detail: **heart-rate zone time bars** (Strava colours), running dynamics
  (cadence, stride, ground contact, vertical oscillation), power, temperature.
- Settings shows the **version and build** of the running image.

Fixed
- A sync interrupted by a restart no longer shows "Syncing…" forever.
- Health-data sync no longer walks back through empty history: "no data" is
  recognised per data type, and history now runs back until it genuinely ends
  (it used to stop a year before your first activity).
- Data-shapes export no longer includes your Garmin account id, device ids,
  timestamps or body measurements.

Upgrading: pull the new image, then run **Re-sync all history** once to collect
health data older than before. Existing data, key and backups carry over.
