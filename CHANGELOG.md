# Changelog

## 0.3.0

New
- **Race predictions** (new Predict tab): 5K, 10K, half marathon and marathon from your
  own best efforts, found inside your runs with a sliding window over the per-second
  distance. Five methods side by side (Riegel 1.06, your own fitted exponent with a 95%
  interval, critical speed, Daniels/Gilbert VDOT, and a conservative 1.15 scenario).
- **Shows its math**: every method prints its formula with your numbers filled in; the
  headline range and median are explained; leave any effort out and watch the result change;
  a back-test against your own earlier efforts; your recent training beside the half and
  marathon; sources and limits on the page; whole calculation downloadable as JSON.
- Mission statement in the README: use your data to train smarter, and always show the math.

Changed
- Best efforts are computed in the background after each sync (and once for existing
  activities after you update), so the first Predict page may say it is still analysing.

Docs
- New [docs/predictions.md](docs/predictions.md). Roadmap: VO2max predictions item.

## 0.2.2

New
- **Phone layout.** Bottom tab bar (Dashboard, Activities, Recovery, Settings),
  charts sized to the screen with readable text, compact tables (less important
  columns hidden), bigger touch targets, no zooming when you tap a field, and a
  scrollable sport filter row.
- **Touch on charts.** Drag a finger along any chart to read values; on the run
  page it also moves the marker on the map. Vertical swipes still scroll the page.

Fixed
- No more sideways scrolling on phone-width screens (the header was about
  700 px wide).

Docs
- Roadmap: transparent race-time predictions (every prediction must show its
  inputs, method, uncertainty and sources); "open and explainable" added to the
  README principles.

## 0.2.1

New
- **Heart-rate zone bands** behind the heart-rate line on run charts, in Strava's
  colours (Z1 grey, Z2 blue, Z3 green, Z4 orange, Z5 red), with a zone legend.
  Zones are estimated from your max heart rate at 50/60/70/80/90% (Garmin's
  defaults). Set your max heart rate in Settings, Preferences; blank uses the
  highest value in your activities. Garmin's own zone settings are also being
  collected for a later, exact version.

Fixed
- **Rolling 7-day longest run** no longer drops off a cliff when you have not
  run yet today: until there is a run today, today's point looks back 8 days.
- Data-shapes export no longer hides harmless running-dynamics fields by
  accident (ground contact time, vertical oscillation).

Docs
- README, install guide and roadmap brought up to date with what is built.

## 0.2.0

New
- **Recovery page**: sleep score and duration (deep/REM), HRV with your balanced
  range, resting heart rate, Body Battery and stress, 30 days to 1 year.
- **Weekly mileage chart** on the dashboard: rolling 7-day total in km per week
  (was km per day), next to the rolling 7-day longest run.
- **Default sport setting** (Settings, Preferences): choose which sport the dashboard opens on
  (Running unless you change it; saved on the server, so it applies on every device).
- Dashboard opens on **Running** by default; new **Hiking** group; treadmill,
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
