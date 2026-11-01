# Race predictions: how they work

Mission: use your data to train smarter, and always show the math. Nothing on the
**Predict** page is a black box. This page explains the whole calculation, and the
page itself shows the same working with your numbers (and the API and the downloadable
JSON contain it too).

## 1. Best efforts (the inputs)

For every running activity with per-second data, the app finds the **fastest stretch
of each standard distance** (1 km, 1 mile, 3 km, 5 km, 10 km, 15 km, half marathon,
30 km, marathon) that fits inside the run. For each possible start sample it finds where
the cumulative distance has grown by exactly that distance (interpolating between
samples), takes the elapsed time, and keeps the smallest. So a 5K can be found inside a
12 km run. Details kept for each effort: time, start point, average heart rate, climb,
and time lost to pauses.

Rules, all visible on the page:
- Treadmill/indoor runs and trail runs are **included by default**. Trail runs are only used while
  grade-adjusted pace is on (below); switches turn either off. Treadmill distances come from a foot pod or watch
  estimate and have no incline data, so they are used as recorded.
- An effort faster than 7 m/s (2:23 per km) is treated as a **GPS glitch** and ignored.
- You can **leave out** any effort and watch the prediction change.
- Efforts are taken from the **last 3, 6, 12 or 24 months** (your choice); the fastest per
  distance in that period is the one used.
- An effort is only used as a source if it lasted **3.5 to 230 minutes**. Riegel's own running data covered 1.5 to 42.2 km
  (3.5 to 129 minutes for men's records, 3.9 to 147 for women's); the app allows up to 230 minutes so slower recreational
  marathons can count, and flags anything outside that window as an extrapolation.

## 2. The methods

| Method | Formula | Source |
| --- | --- | --- |
| Riegel, k = 1.06 | T2 = T1 x (D2 / D1)^1.06, from the effort nearest in distance | Riegel (1981) |
| Your fitted exponent | Least-squares line through ln(time) versus ln(distance) of your efforts; slope is your personal k. Needs 3 or more distances; gives a 95% prediction interval | Riegel (1981), method |
| Critical speed | distance = CS x time + D' fitted to efforts of 2 to 30 minutes; time = (D - D') / CS. Counted only when the predicted time is inside 2 to 30 minutes | Poole et al. (2016); the 2 to 40 minute window is this app's rule |
| VDOT | Daniels/Gilbert oxygen-cost and %VO2max-versus-duration equations give a VDOT; the equations are then solved for the target distance | Daniels & Gilbert (1979) |
| Conservative scenario, k = 1.15 | Riegel with k = 1.15 | Fetch Everyone analysis (not peer reviewed) |

Every method prints its own steps with your numbers substituted.

### Grade-adjusted pace (hills, trail)

Treadmill and trail runs are included by default; trail runs only while grade-adjusted pace (GAP) is on.
For every step of a run the app measures the grade (altitude change over +/- 25 m, capped at +/-30% because
steeper readings are almost always altitude noise) and multiplies the real distance by Minetti's energy-cost
ratio for that grade: cost(i) = 155.4 i^5 - 30.4 i^4 - 43.3 i^3 + 46.3 i^2 + 19.5 i + 3.6 (J per kg per metre,
i = slope as a fraction), ratio = cost(i) / 3.6. The sum is the **flat-equivalent distance**, and best efforts
are found on that axis. Treadmill runs have no altitude, so they are unchanged. The Predict page shows the
cost table and, for every adjusted effort, how many real kilometres counted as how many flat kilometres.

Source: Minetti AE, Moia C, Roi GS, Susta D, Ferretti G. Energy cost of walking and running at extreme uphill and
downhill slopes. *J Appl Physiol* 93:1039-1046, 2002 (polynomial verified against the full text). Limits, from the
paper: 10 elite mountain-endurance men on a smooth treadmill; measured level cost 3.40 +/- 0.24 versus 3.6 from
the fit; downhill running was about 40% cheaper than earlier data from sedentary people; rougher ground than a
treadmill raises the cost. Adjusted times are therefore approximate.

## 3. The headline

The big number is the **median** of the methods that are counted, and the range is the
**fastest to slowest** of them. Methods marked *reference only* (outside their valid
range) or *not enough data* are shown but not counted. This is deliberately simple so you
can check it by hand.

## 4. How much to trust it

- **Support rating** (the app's own rule of thumb, not from the literature): a target up
  to 1.5x the longest effort used is well supported, up to 3x is extrapolated, beyond that
  is weak.
- **Back-test**: for each of your own efforts at the target distance that was your fastest
  within 60 days either side (a stand-in for a race), the app predicts it using only efforts
  from the 90 days before and reports the error. Your best efforts include training runs
  that were not all-out, so expect predictions to look optimistic.
- **Training context**: for the half and marathon the page shows your average weekly
  distance and longest run over 8 weeks. No adjustment is made for them.

## 5. Marked races

Mark an activity as a race on its page. Once you have three or more at a distance, the back-test
uses them (instead of "fastest within 60 days") and lists each race with what each method would
have predicted from the 90 days before it.

## 6. Max heart rate from your own data

For each activity the app drops heart-rate samples outside 40 to 230 bpm, drops one-sample spikes
(more than 20 bpm from both neighbours while the neighbours agree), and takes the highest 15-second
rolling average. Your estimate is the **median of your three highest activity peaks** in the last two
years, so a single glitch cannot set it; with fewer than three it uses the highest and says the confidence
is low. The age formula of Tanaka, Monahan & Seals (208 - 0.7 x age) is shown only as a sanity check.
Age formulas carry roughly 9 to 10 bpm of individual error in endurance athletes (Kasiak et al. 2023).
Zone bands use a common five-zone convention (50/60/70/80/90% of max); this is not claimed to be your
Garmin's own boundaries.

## 7. VO2max estimates

Several methods side by side, none a measured VO2max: VDOT from your race performance (a performance
index), and the heart rate ratio method 15.3 x HRmax / HRrest (Uth et al. 2004; constant from 10 well-trained
men; +/- 4.7 ml/kg/min shown; resting-heart-rate methods tend to read high, Molina-Garcia et al. 2022).
You can enter your watch's value to compare, since Garmin does not share it through its Personal API.

## 8. Known limits

- Predictions are least reliable far beyond the distances you have run, especially the
  marathon, which depends on endurance training that shorter efforts do not capture.
- Garmin's own splits are not used as a cross-check yet.
- Sources were checked from abstracts and secondary summaries, not the full papers.
- Not medical advice.

## Sources

- Riegel PS. Athletic records and human endurance. *American Scientist* 69(3):285-290, 1981.
- Minetti AE, Moia C, Roi GS, Susta D, Ferretti G. Energy cost of walking and running at extreme uphill and downhill slopes. *J Appl Physiol* 93:1039-1046, 2002. <https://doi.org/10.1152/japplphysiol.01177.2001>
- Daniels J, Gilbert J. *Oxygen Power: Performance Tables for Distance Runners*, 1979; Daniels J. *Daniels' Running Formula*.
- Poole DC, Burnley M, Vanhatalo A, Rossiter HB, Jones AM. Critical power: an important fatigue threshold in exercise physiology. *Med Sci Sports Exerc* 48(11):2320-2334, 2016. <https://pmc.ncbi.nlm.nih.gov/articles/PMC5070974>
- Fetch Everyone marathon-prediction analysis (not peer reviewed). <https://www.fetcheveryone.com/article/marathon-time-prediction-37>
- Valencia Marathon prediction study (2025). <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12856576/>
