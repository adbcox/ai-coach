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
- Treadmill/indoor runs and trail runs are **left out by default** (their distance is
  less reliable, or terrain distorts pace); switches turn them on.
- An effort faster than 7 m/s (2:23 per km) is treated as a **GPS glitch** and ignored.
- You can **leave out** any effort and watch the prediction change.
- Efforts are taken from the **last 3, 6, 12 or 24 months** (your choice); the fastest per
  distance in that period is the one used.
- An effort is only used as a source if it lasted **3.5 to 230 minutes**, the range
  Riegel's formula was fitted to.

## 2. The methods

| Method | Formula | Source |
| --- | --- | --- |
| Riegel, k = 1.06 | T2 = T1 x (D2 / D1)^1.06, from the effort nearest in distance | Riegel (1981) |
| Your fitted exponent | Least-squares line through ln(time) versus ln(distance) of your efforts; slope is your personal k. Needs 3 or more distances; gives a 95% prediction interval | Riegel (1981), method |
| Critical speed | distance = CS x time + D' fitted to efforts of 2 to 40 minutes; time = (D - D') / CS. Counted only when the predicted time is inside 2 to 40 minutes | Poole et al. (2016); the 2 to 40 minute window is this app's rule |
| VDOT | Daniels/Gilbert oxygen-cost and %VO2max-versus-duration equations give a VDOT; the equations are then solved for the target distance | Daniels & Gilbert (1979) |
| Conservative scenario, k = 1.15 | Riegel with k = 1.15 | Fetch Everyone analysis (not peer reviewed) |

Every method prints its own steps with your numbers substituted.

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

## 5. Known limits

- Predictions are least reliable far beyond the distances you have run, especially the
  marathon, which depends on endurance training that shorter efforts do not capture.
- Garmin's own splits are not used as a cross-check yet, and there is no hill (grade)
  adjustment.
- Sources were checked from abstracts and secondary summaries, not the full papers.
- Not medical advice.

## Sources

- Riegel PS. Athletic records and human endurance. *American Scientist* 69(3):285-290, 1981.
- Daniels J, Gilbert J. *Oxygen Power: Performance Tables for Distance Runners*, 1979; Daniels J. *Daniels' Running Formula*.
- Poole DC, Burnley M, Vanhatalo A, Rossiter HB, Jones AM. Critical power: an important fatigue threshold in exercise physiology. *Med Sci Sports Exerc* 48(11):2320-2334, 2016. <https://pmc.ncbi.nlm.nih.gov/articles/PMC5070974>
- Fetch Everyone marathon-prediction analysis (not peer reviewed). <https://www.fetcheveryone.com/article/marathon-time-prediction-37>
- Valencia Marathon prediction study (2025). <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12856576/>
