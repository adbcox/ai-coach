# Changelog

## 0.4.3

Added
- **About you** in Settings: sex, year of birth (shows your age) and weight. Weight is pulled from the Garmin weight
  data the app already syncs (latest value and its date shown); type a value to override it, clear the box to go back
  to Garmin's. Nothing uses these yet except showing them; they are the inputs the upcoming formulas will need, and each
  formula will say when it uses one. A `/api/weight` history endpoint is ready for a trend chart.
- Garmin's weight layout is read defensively (it is not documented and has not been checked against a real account's
  data), and Settings says plainly when no weight is found.

## 0.4.2

Changed
- **Five more papers read in full** (supplied by the app's author): Kasiak 2023 (max heart rate equations in 5,069 athletes), Wiecha 2023 (PLOS ONE, VO2max equations in athletes), Wiecha 2023 (eLife, submaximal models), Hata 2025 (HYPAC), Latorre-Roman 2025 (Valencia Marathon pacing). The Frontiers entry had the wrong authors and a guessed title; now corrected. HYPAC and eLife do not unlock a watch-only VO2max method (lab gas data needed; 10-student validation), so none of them changed a calculation.
- **Five sources are now read in full** (supplied by the app's author): Riegel 1981, Uth 2004 (with its 2005
  erratum), Tanaka 2001, Poole 2016 and the INTERLIVE wearable VO2max meta-analysis (Molina-Garcia 2022). Their
  entries in Sources and credits now say "full text" and quote what the papers actually report.
- Critical-speed window shortened from 2-40 to 2-30 minutes: Poole et al. say exercise above critical power lasts
  "perhaps 30 minutes" at most, so 40 went beyond the source.

Corrected (claims the full texts did not support)
- Riegel's 1981 paper does not give k = 1.06 for runners. It reports 1.077 (men's world records), 1.083 (women's)
  and 1.05-1.06 for men over 40. 1.06 is widely used and credited to his 1977 Runner's World article, which has not
  been read. The app still uses 1.06 and your own fitted exponent, and now says exactly this.
- The "3.5 to 230 minutes" range is not Riegel's: his running data covered 1.5-42.2 km (3.5-129 min men, 3.9-147 min
  women). 230 minutes is now labelled as the app's own rule.
- The heart-rate-ratio VO2max range (+/-4.7) is Uth's error with age-predicted HRmax; with lab-measured HRmax it
  was 2.7. The card now says why the larger one is used, and quotes the INTERLIVE numbers (resting-data wearables
  read about 2.2 ml/kg/min high, individual differences about -13 to +17).

## 0.4.1

Changed
- **Calmer screens.** The Predict page opens with just the four predictions, a one-line explanation each, and a
  compact VO2max card. All the working (efforts, methods, back-test, formulas, sources) sits behind "Show the
  math", nothing expanded by default (134 words visible instead of about 2,700). Settings text trimmed the same way.
- VO2max methods now show the age of the research they are based on (1979 and 2004), and the card says
  plainly that these are older models for tracking trends.

Fixed
- The phone tab bar no longer appears at the bottom of the desktop layout.

Docs
- References: newer VO2max evidence recorded (not used in any calculation yet): a 2024 critique of the ACSM
  running-cost equation, a 2023 eLife submaximal-prediction study, an ACSM-in-athletes study, and the Firstbeat white
  paper behind Garmin's own number, each labelled with how well it was checked. VDOT's limits now mention that
  a 2020 study of marathoners related it to running economy rather than laboratory VO2max.

## 0.4.0

New
- **Grade-adjusted pace** for hills and trails (Minetti et al. 2002; the polynomial was checked against the
  paper's full text). Treadmill and trail runs are now **included by default**; trail runs only while grade
  adjustment is on. Each adjusted effort says how many real kilometres counted as how many flat kilometres.
- **Max heart rate from your own data**: median of your three highest sustained peaks (glitches filtered), with the
  working, the peaks table and a button to use it; the zone bands follow it. Age formula shown only as a comparison.
- **Mark an activity as a race**; predictions are then checked against your real races.
- **VO2max estimates** (VDOT from race performance, heart rate ratio), each with its working, range and limits, plus a
  field for your watch's value to compare.
- **References and credits**: one bibliography for the whole app. Every method names its source with a clickable
  credit; the References page (and docs/references.md) show full citations, what each is used for, limits, and how well
  each source was checked.

Fixed
- Removed a claim I could not verify: the zone bands are now described as a common five-zone convention, not "Garmin's
  default zones" (Garmin's manuals say defaults come from your profile and can differ).

Changed
- Best efforts are recomputed once after updating (new grade-adjusted and heart-rate data); the Predict page shows progress.

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
  Zones are estimated from your max heart rate using a common five-zone convention
  (50/60/70/80/90%); Garmin's own boundaries may differ. Set your max heart rate in Settings, Preferences; blank uses the
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
