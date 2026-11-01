# References and credits

<!-- Generated from backend/app/references.py by `python -m app.references`. Do not edit by hand. -->

Mission: use your data to train smarter, and always show the math. That includes crediting the people whose work the math comes from, and being honest about how well each source has been checked. Every method in the app names its sources, and the app's References page shows the same list.

**How well each source was checked**

- **full text**: Full text read and checked against what the app does
- **abstract**: Abstract and summaries read; full text not yet checked
- **secondary**: Known from secondary sources (summaries, vendor pages); the original was not read
- **documentation**: Vendor documentation read via search summaries

## Minetti et al. 2002

Minetti AE, Moia C, Roi GS, Susta D, Ferretti G (2002). Energy cost of walking and running at extreme uphill and downhill slopes. Journal of Applied Physiology 93(3):1039-1046. doi:10.1152/japplphysiol.01177.2001

- Link: <https://doi.org/10.1152/japplphysiol.01177.2001>
- Checked: **Full text read and checked against what the app does**. Full text read (PDF supplied by the app's author). The polynomial below is the equation printed in the legend of Fig. 1 (p. 1041); Table 2 (p. 1042) values match its predictions.
- Used for: Grade-adjusted pace (hills and trail runs)
- How the app uses it: The energy cost of running on a slope i is Cr(i) = 155.4 i^5 - 30.4 i^4 - 43.3 i^3 + 46.3 i^2 + 19.5 i + 3.6 (J per kg per metre, R2 = 0.999, slopes -0.45 to +0.45). The app multiplies each step's real distance by Cr(i) / 3.6 to get flat-equivalent distance.
- Limits: Ten elite mountain-endurance men on a smooth treadmill. Measured level cost 3.40 +/- 0.24 versus 3.6 from the fit; downhill running was about 40% cheaper than earlier data from sedentary people; the authors note rougher ground raises the cost. Adjusted times are therefore approximate.

## Riegel 1981

Riegel PS (1981). Athletic records and human endurance. American Scientist 69(3):285-290 (an earlier version, 'Time Predicting', appeared in Runner's World in 1977).

- Link: <https://en.wikipedia.org/wiki/Peter_Riegel>
- Checked: **Abstract and summaries read; full text not yet checked**. Abstract and secondary summaries only. The commonly quoted form T2 = T1 x (D2/D1)^1.06 and the 3.5 to 230 minute range come from those summaries, not the paper itself.
- Used for: Riegel power law (k = 1.06); Your fitted exponent; Source-effort duration range (3.5 to 230 minutes)
- How the app uses it: Time over a new distance = known time x (new distance / known distance)^k. The app uses k = 1.06 as the textbook value and also fits k to the athlete's own efforts.
- Limits: Fitted to world-record-type data; the author's range was about 3.5 to 230 minutes. Many recreational runners slow down more than k = 1.06 implies over long distances.

## Daniels & Gilbert 1979

Daniels J, Gilbert J (1979). Oxygen Power: Performance Tables for Distance Runners (see also Daniels' Running Formula, Human Kinetics). Self-published, 1979.

- Link: <https://en.wikipedia.org/wiki/Jack_Daniels_(coach)>
- Checked: **Known from secondary sources (summaries, vendor pages); the original was not read**. Equation constants confirmed from secondary sources (calculator and coaching pages). The app's implementation reproduces the widely quoted value (a 20:00 5K gives a VDOT of 49.8); the book itself was not read.
- Used for: VDOT race-time prediction; VDOT as a race-performance fitness index (VO2max section)
- How the app uses it: oxygen cost = -4.60 + 0.182258 v + 0.000104 v^2 (v in m/min); fraction of VO2max held = 0.8 + 0.1894393 e^(-0.012778 t) + 0.2989558 e^(-0.1932605 t) (t in minutes); VDOT = cost / fraction. Solved for the target distance.
- Limits: VDOT is a performance score, not a measured VO2max. It assumes the athlete has the endurance base for the distance being predicted.

## Poole et al. 2016

Poole DC, Burnley M, Vanhatalo A, Rossiter HB, Jones AM (2016). Critical power: an important fatigue threshold in exercise physiology. Medicine & Science in Sports & Exercise 48(11):2320-2334. doi:10.1249/MSS.0000000000000939

- Link: <https://pmc.ncbi.nlm.nih.gov/articles/PMC5070974>
- Checked: **Abstract and summaries read; full text not yet checked**. Abstract and search summaries read; full text (free on PubMed Central) not yet checked.
- Used for: Critical speed prediction
- How the app uses it: Two-parameter model: distance = CS x time + D'. Fitted by least squares to the athlete's 2 to 40 minute efforts.
- Limits: The 2 to 40 minute window in which the app counts this method is the app's own conservative rule of thumb, not a limit stated in the paper.

## Uth et al. 2004

Uth N, Sorensen H, Overgaard K, Pedersen PK (2004). Estimation of VO2max from the ratio between HRmax and HRrest - the Heart Rate Ratio Method. European Journal of Applied Physiology (2004).

- Link: <https://www.springermedizin.de/estimation-of-vo2max-from-the-ratio-between-hrmax-and-hrrest-the/8478242>
- Checked: **Abstract and summaries read; full text not yet checked**. Abstract and search summaries read. Volume and page numbers are not given here because they were not verified.
- Used for: Heart rate ratio VO2max estimate
- How the app uses it: VO2max (ml/kg/min) = 15.3 x HRmax / HRrest. The range shown uses the reported standard error of 4.7 ml/kg/min.
- Limits: The constant came from a subgroup of 10 well-trained men; the authors say other groups need direct validation. The 4.7 error (about 7.8%) was with age-predicted HRmax.

## Molina-Garcia et al. 2022

Molina-Garcia P, et al. (INTERLIVE Network) (2022). Validity of estimating the maximal oxygen consumption by consumer wearables: a systematic review with meta-analysis and expert statement of the INTERLIVE Network. Sports Medicine (2022).

- Link: <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9213394/>
- Checked: **Abstract and summaries read; full text not yet checked**. Abstract and search summaries read; full text not yet checked.
- Used for: Cautions on VO2max estimates (resting-data methods tend to read high; individual error stays large)
- How the app uses it: Not a formula. It is why the app shows several VO2max methods with ranges and flags the resting-heart-rate method.
- Limits: A review of consumer wearables, not of the specific equations used here.

## Tanaka et al. 2001

Tanaka H, Monahan KD, Seals DR (2001). Age-predicted maximal heart rate revisited. Journal of the American College of Cardiology 37(1):153-156.

- Link: <https://pubmed.ncbi.nlm.nih.gov/11153730/>
- Checked: **Abstract and summaries read; full text not yet checked**. PubMed abstract read via search summaries (equation 208 - 0.7 x age; strong negative correlation of HRmax with age, r = -0.90). Full text not read.
- Used for: Age-based max heart rate comparison
- How the app uses it: HRmax = 208 - 0.7 x age, shown beside your own measured peaks as a sanity check, never used as the estimate.
- Limits: A population equation: individual error is large (see Kasiak et al. 2023).

## Kasiak et al. 2023

Kasiak P, et al. (2023). Validity of the maximal heart rate prediction models among runners and cyclists. Journal of Clinical Medicine (2023).

- Link: <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10146295/>
- Checked: **Abstract and summaries read; full text not yet checked**. Abstract and search summaries read (5,069 endurance athletes tested against maximal exercise tests; 9 of 13 equations differed significantly from measured values; RMSE 9.1 to 10.5 bpm).
- Used for: Why max heart rate is estimated from your own peaks rather than an age formula
- How the app uses it: Evidence that age formulas carry errors of roughly 9 to 10 bpm for individual endurance athletes.
- Limits: Laboratory tests; the authors recommend predictions only as a supplement to testing.

## Valencia Marathon study 2025

See source (2025). Performance prediction equation for the Valencia Marathon based on time and pacing in the half marathon. Open-access journal (see link).

- Link: <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12856576/>
- Checked: **Abstract and summaries read; full text not yet checked**. Abstract only. Reported accuracy similar to the VDOT system but behaving differently by runner level.
- Used for: Context for half-to-marathon prediction and for showing several methods side by side
- How the app uses it: Not a formula used by the app; informs the choice to show methods together instead of picking one.
- Limits: One race, one population.

## Fetch Everyone analysis

Fetch Everyone (website). Marathon time prediction. Website analysis, not peer reviewed.

- Link: <https://www.fetcheveryone.com/article/marathon-time-prediction-37>
- Checked: **Known from secondary sources (summaries, vendor pages); the original was not read**. Read via search summaries. Reported: 1,071 marathoners with 5+ half and 5+ full marathons; fewer than 5% matched k = 1.06 predictions; effective exponents were often nearer 1.15.
- Used for: Conservative scenario (Riegel k = 1.15)
- How the app uses it: Only to set a deliberately cautious scenario beside the standard k = 1.06.
- Limits: Not peer reviewed; experienced runners, not typical recreational runners.

## Garmin manual: heart rate zones

Garmin Ltd.. Setting your heart rate zones (owner's manual). Garmin documentation.

- Link: <https://www8.garmin.com/manuals/webhelp/instinct/EN-US/GUID-30C91919-943C-44E9-8048-901AC0881AEA.html>
- Checked: **Vendor documentation read via search summaries**. Read via search summaries: default zones come from your profile, can be shown as % of max heart rate or % of heart rate reserve, and can be edited. The specific default percentages could NOT be confirmed.
- Used for: Why the app's zone bands are labelled an estimate
- How the app uses it: The app draws zones using a common five-zone convention (50/60/70/80/90% of max heart rate). It does not claim these are your Garmin's boundaries; reading your real ones is on the roadmap.
- Limits: Your watch's zones may differ.

## Software and data credits

- Garmin Connect Personal API; endpoint paths follow Garmin's published Python client (<https://github.com/garmin/connect-personal-api-python>, Apache-2.0). No code was copied.
- Map tiles and data: (c) OpenStreetMap contributors (<https://www.openstreetmap.org/copyright>), shown on every map.
- Libraries: see [licenses](licenses.md) (Leaflet, uPlot, FastAPI, React, Docling and others).

