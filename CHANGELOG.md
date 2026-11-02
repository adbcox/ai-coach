# Changelog

## 0.6.4

Added
- **Exact values on the activity charts.** Point at (or touch and drag along) any chart and a pop-up shows the exact value and where
  you are in the run (e.g. "154 bpm at 7.44 mi"), with a marker on the line. The current value of every chart is also shown at the
  right of its title, so one position reads pace, heart rate, elevation and cadence at once.

Fixed
- The charts now line up exactly (the last one was slightly narrower, so the cursor line sat in a different place on each chart).
- **Cadence on running charts is now steps per minute** (e.g. 172 instead of 86), matching Garmin Connect and the laps table. Garmin's
  file stores strides per minute (one foot); rides still show rpm.

## 0.6.3

A roll-up so everything since 0.6.0 can be tested in one install. Nothing new beyond what is listed under 0.6.1 and 0.6.2:
- **Laps (Garmin's splits)** on every activity page (0.6.1): the 1 km automatic laps, manual laps or workout steps with time, pace,
  heart rate, elevation, cadence and power, filled in for your existing activities from the files already on your server.
- **Automatic OCR** for scanned PDFs and pictures, and **much cleaner PDF text** (0.6.2), with your existing papers re-converted
  automatically.

## 0.6.2

Added
- **Scanned PDFs and pictures are read automatically (OCR).** No more "needs OCR" to deal with: drop a scan, a screenshot or a
  photo of a page (.png, .jpg, .tif, .webp) and it is read in the background with Tesseract, page by page, with a live
  "page 3 of 6" and the finished text appearing by itself. Everything runs on your server. Scans already in your Library
  (such as an old paper that said "needs OCR") are picked up automatically after the update.
- Every OCR'd item says so, shows its average confidence, lists any low-confidence pages, and warns that OCR can misread
  digits, symbols and equations. Tested on a real 6-page scan (a 1981 journal article): 94% confidence, about 17 seconds in
  total, and every table value checked against the original was read correctly; an exponent in an equation was misread, which is
  exactly why the warning is there.

Changed
- **Much cleaner conversion of PDFs** (and OCR text): words split across lines ("monitor -" then "ing") are rejoined, hard line
  breaks inside a paragraph are joined into real paragraphs, ligatures (fi, fl, ffi) and soft hyphens are normalised, and running
  page headers and page numbers are removed. Words the document itself writes with a hyphen (high-intensity) keep it.
- **Your existing papers are re-converted automatically** from their stored originals after the update, in the background. Your
  tags, notes, details and "reviewed" flags are kept untouched. (This happens again only when the converter improves.)
- The image grows by about 60 MB for Tesseract and the page renderer.

Notes
- Tables, figures, equations and two-column layouts still do not convert faithfully; a layout-aware converter is the next step for
  those (it needs no AI). OCR language defaults to English (`AEC_OCR_LANGS`, e.g. `eng+fra`, needs the extra language data in the image).

## 0.6.1

Added
- **Laps (Garmin's splits)** on every activity page: each automatic 1 km lap (or manual lap, or workout step) with distance, time, pace
  (or speed for rides), average and max heart rate, elevation gain and loss, cadence and power, plus a bar chart of lap pace with the
  fastest full lap marked. Workout steps are labelled warm-up / interval / rest / cool-down. They come from the activity file Garmin
  already sends, so they match Garmin Connect and need no extra Garmin requests.
- Activities you already have are filled in automatically from the files stored on your server (in the background after the update,
  and instantly when you open an activity).

Notes
- A short final lap shows its real distance (the remainder), and only full-length automatic splits are ranked fastest.
- Cadence for running laps is shown as steps per minute (Garmin files store strides per minute for one foot).

## 0.6.0

Added
- **Library** (new tab): feed in a bunch of papers. Drop PDFs, web pages (.html), Markdown or text, many at once, or paste a
  link or a DOI, or type a citation. Every source becomes a real Markdown file (with a header holding title, authors, year,
  DOI and how it was converted) in `ingest/2-fulltext/`, the untouched original in `ingest/3-source/`, and optionally your own
  notes in `ingest/1-actionable/`. No AI is involved: conversion uses pypdf and trafilatura.
- Read each paper in the app (rendered Markdown, or the raw file), search across titles, authors, tags, your notes and the
  full text with highlighted matches, filter by tag or "needs attention" / "not reviewed", edit details, tags and evidence type,
  mark a source "reviewed", and write notes from the three-tier template (draft until you mark them reviewed).
- DOIs are looked up on Crossref (only the DOI is sent) to fill in authors, year and journal, also for uploaded PDFs that contain a
  DOI. Duplicates are caught by file hash and DOI.
- Attach your own copy of any source the app cites (they are listed in the Library and on the Sources and credits page).
- Drop files into `ingest/inbox/` on the server and they are converted within a minute (or press Scan folder). Files you write
  or copy into the folders by hand are picked up too: the files are the source of truth and the search index is rebuilt from them.
- Scanned PDFs are kept and flagged "needs OCR" rather than silently producing nothing; "Convert again" re-runs a conversion
  from the original and keeps everything you wrote.

Security and privacy
- Links can only point at public internet addresses (not this machine or your network), including after redirects; downloads are
  size-limited; Markdown is rendered with raw HTML switched off and images not loaded.
- Papers are stored only in your data volume. They are included in your backups, never in git (`*.pdf` is ignored) or the image.

Notes
- The image grows by about 40 MB (pypdf, trafilatura and its HTML tools).
- PDF conversion is text extraction: tables, figures and equations can come out garbled. Every item says so and keeps the original.

## 0.5.1

Changed
- **Times are never decimals.** Every duration now reads as m:ss, h:mm or h:mm:ss as appropriate. The last decimal
  time in the app, the minutes axis on activity charts without a distance (e.g. treadmill runs), is now m:ss or
  h:mm:ss. Sleep (0.4.6), activity times, predictions, paces and the relative "x min ago" labels already followed this.

## 0.5.0

A roll-up of the 0.4.2 to 0.4.7 fixes and adjustments below, in one install.

Added
- **About you** (Settings): sex, birthday (exact age), weight (pulled from your synced Garmin data, overridable) and
  height. Not used in any calculation yet; each future formula will say when it uses one.
- **Choosable units**: km or miles, metres or feet, kg or pounds, cm or feet and inches. Applies across the dashboard,
  activities, charts, activity page and Predict; the written working stays metric to match the papers.
- **Version badge** next to the name in the header and on the sign-in page.

Changed
- **Evidence**: eleven sources read in full and quoted accurately in Sources and credits (Riegel, Uth, Tanaka, Poole,
  INTERLIVE, Kasiak, both Wiecha 2023 papers, HYPAC, Latorre-Roman and Minetti). Corrections: Riegel's paper gives 1.077 / 1.083
  (world records), not 1.06; his time window is not 3.5 to 230 minutes; the critical-speed window is now 2 to 30 minutes
  (Poole et al.); the heart-rate-ratio error range is explained (4.7 with age-predicted max HR, 2.7 with lab-measured).
- Sleep shows as hours:minutes (6:12, not 6.2 h).

Fixed
- Distances in Latest activities no longer wrap onto two lines.
- Typing feet then inches no longer saves half the height.
- Copyrighted papers can never be committed or baked into the image (`*.pdf` and `*.epub` are ignored by git and Docker).

## 0.4.7

Added
- **Version badge** (e.g. v0.4.7) next to the name in the header and on the sign-in page, so you can see which build you are on. Hover or long-press it for the build id.

## 0.4.6

Changed
- Sleep durations now read as hours:minutes (6:12 instead of 6.2 h) on the Recovery tile, the chart readout and the chart axis.

## 0.4.5

Fixed
- Distances in the dashboard's Latest activities list no longer wrap ("7.19" above "km") on a wide screen.

## 0.4.4

Added
- **Units you can choose** (Settings → Units): distance, pace and speed (km or miles), elevation (m or feet),
  weight (kg or pounds) and height (cm or feet and inches). Applied across the dashboard, activities, charts, the
  activity page and Predict. Everything is stored in metric; only the display changes. The working shown under
  "Show the math" stays metric so it matches the papers.
- **Height** (optional) in Settings → About you.

Changed
- **Birthday instead of birth year** (a date picker); your exact age is shown and used for the age-formula comparison.
  A birth year you entered earlier is still honoured until you set a birthday.

Fixed
- Typing feet then inches no longer saves half the value (found while testing).

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
