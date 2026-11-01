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
- Checked: **Full text read and checked against what the app does**. Full text read (scanned PDF supplied by the app's author). Table 1 gives t = a x^b fitted to world records up to 1 Nov 1979. Running, men: a = 2.299, b = 1.07732 (1.5 to 42.2 km, 3.5 to 129 min); women: b = 1.08283 (3.9 to 147 min); men over 40, 50, 60, 70: b = 1.0535, 1.0537, 1.0560, 1.0637. The text calls the world-class value 1.08 and the older-men value 1.05 to 1.06. The commonly quoted k = 1.06 is NOT stated for general runners in this paper; it is usually credited to Riegel's 1977 Runner's World article (reference 1 in the paper), which has not been read.
- Used for: Riegel power law (k = 1.06); Your fitted exponent; Source-effort distance range (1.5 to 42.2 km)
- How the app uses it: Time over a new distance = known time x (new distance / known distance)^k. The app uses k = 1.06 as the widely used value and also fits k to the athlete's own efforts. The 3.5 to 230 minute window is the app's own rule.
- Limits: Fitted to world records (men and women), not to individual recreational runners; the paper's own exponents were 1.077 (men) and 1.083 (women), higher than 1.06. The 1981 data stop at 1 Nov 1979. The author notes records are ephemeral and that the power function is a compromise between accuracy and simplicity, not a theory of locomotion.

## Daniels & Gilbert 1979

Daniels J, Gilbert J (1979). Oxygen Power: Performance Tables for Distance Runners (see also Daniels' Running Formula, Human Kinetics). Self-published, 1979.

- Link: <https://en.wikipedia.org/wiki/Jack_Daniels_(coach)>
- Checked: **Known from secondary sources (summaries, vendor pages); the original was not read**. Equation constants confirmed from secondary sources (calculator and coaching pages). The app's implementation reproduces the widely quoted value (a 20:00 5K gives a VDOT of 49.8); the book itself was not read.
- Used for: VDOT race-time prediction; VDOT as a race-performance fitness index (VO2max section)
- How the app uses it: oxygen cost = -4.60 + 0.182258 v + 0.000104 v^2 (v in m/min); fraction of VO2max held = 0.8 + 0.1894393 e^(-0.012778 t) + 0.2989558 e^(-0.1932605 t) (t in minutes); VDOT = cost / fraction. Solved for the target distance.
- Limits: A 1979 model from competitive runners' performances. VDOT is a performance score, not a measured VO2max: it mixes aerobic capacity with running economy, and one 2020 study of experienced marathoners found it related to a running-economy measure but not to laboratory VO2max. It assumes the endurance base for the distance being predicted.

## Poole et al. 2016

Poole DC, Burnley M, Vanhatalo A, Rossiter HB, Jones AM (2016). Critical power: an important fatigue threshold in exercise physiology. Medicine & Science in Sports & Exercise 48(11):2320-2334. doi:10.1249/MSS.0000000000000939

- Link: <https://pmc.ncbi.nlm.nih.gov/articles/PMC5070974>
- Checked: **Full text read and checked against what the app does**. Full text read (author manuscript). The paper says exercise above critical power can be sustained for 'perhaps 30 minutes' at most, and describes CP determination from efforts lasting about 2 to 15 minutes. Written mostly about power (cycling, knee-extension); critical speed for running follows the same hyperbolic form.
- Used for: Critical speed prediction
- How the app uses it: Two-parameter model: distance = CS x time + D'. Fitted by least squares to the athlete's 2 to 30 minute efforts.
- Limits: The paper's 'perhaps 30 minutes' is the upper end for exercise above CP, so the app stops at 30 minutes (earlier versions used 40, which was beyond what the source supports). The exact 2 to 30 window is the app's own choice.

## Uth et al. 2004

Uth N, Sorensen H, Overgaard K, Pedersen PK (2004). Estimation of VO2max from the ratio between HRmax and HRrest - the Heart Rate Ratio Method. European Journal of Applied Physiology 91:111-115. doi:10.1007/s00421-003-0988-y

- Link: <https://www.springermedizin.de/estimation-of-vo2max-from-the-ratio-between-hrmax-and-hrrest-the/8478242>
- Checked: **Full text read and checked against what the app does**. Full text read, including the 2005 erratum (Eur J Appl Physiol 2004 online 17 Nov; it corrects only the Appendix derivation, not the results). 46 well-trained men aged 21 to 51; factor 15.3 (SD 0.7) from a subgroup of 10; the other 36: SEE 2.7 ml/kg/min (4.5%) with measured HRmax, 4.7 (7.8%) with age-predicted HRmax. Resting VO2 was assumed to be 3.4 ml/kg/min.
- Used for: Heart rate ratio VO2max estimate
- How the app uses it: VO2max (ml/kg/min) = 15.3 x HRmax / HRrest. The range shown uses 4.7 ml/kg/min, the larger of the two reported errors (age-predicted HRmax); with a lab-measured HRmax the paper reports 2.7.
- Limits: The constant came from a subgroup of 10 well-trained men; the authors say other groups need direct validation. The 4.7 error (about 7.8%) was with age-predicted HRmax.

## Molina-Garcia et al. 2022

Molina-Garcia P, et al. (INTERLIVE Network) (2022). Validity of estimating the maximal oxygen consumption by consumer wearables: a systematic review with meta-analysis and expert statement of the INTERLIVE Network. Sports Medicine 52:1577-1597. doi:10.1007/s40279-021-01639-y

- Link: <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9213394/>
- Checked: **Full text read and checked against what the app does**. Full text read. 14 validation studies, 403 participants. Wearables using resting-condition data: bias +2.17 ml/kg/min, limits of agreement -13.07 to +17.41. Exercise-based algorithms: bias -0.09, limits -9.92 to +9.74. Several included studies used Garmin devices.
- Used for: Cautions on VO2max estimates (resting-data methods tend to read high; individual error stays large)
- How the app uses it: Not a formula. It is why the app shows several VO2max methods with ranges and flags the resting-heart-rate method.
- Limits: A review of consumer wearables, not of the specific equations used here. The heart-rate-ratio method is resting-based, so expect a high bias of about 2 ml/kg/min and an individual error of roughly +/-15; a watch's exercise-based value is the better number when you have it.

## Tanaka et al. 2001

Tanaka H, Monahan KD, Seals DR (2001). Age-predicted maximal heart rate revisited. Journal of the American College of Cardiology 37(1):153-156.

- Link: <https://pubmed.ncbi.nlm.nih.gov/11153730/>
- Checked: **Full text read and checked against what the app does**. Full text read. Meta-analysis of 351 studies (492 groups, 18,712 subjects): HRmax = 208 - 0.7 x age (r = -0.90); a lab study of 514 healthy adults gave 209 - 0.7 x age. Scatter around the line is about 10 beats/min (SD).
- Used for: Age-based max heart rate comparison
- How the app uses it: HRmax = 208 - 0.7 x age, shown beside your own measured peaks as a sanity check, never used as the estimate.
- Limits: A population equation: individual error is large (see Kasiak et al. 2023).

## Kasiak et al. 2023

Kasiak PS, Wiecha S, Cieslinski I, Takken T, Lach J, Lewandowski M, Barylski M, Mamcarz A, Sliz D (2023). Validity of the maximal heart rate prediction models among runners and cyclists. Journal of Clinical Medicine 12(8):2884. doi:10.3390/jcm12082884

- Link: <https://doi.org/10.3390/jcm12082884>
- Checked: **Full text read and checked against what the app does**. Full text read. 4,043 runners (age 33.6, 83.5% men) and 1,026 cyclists tested to maximum in the laboratory. Measured HRmax in runners 184.6 (SD 9.8) bpm. 13 equations compared: 9 differed significantly from measured; RMSE 9.1 to 10.5 bpm; MAPE up to 4.7%. Tanaka in runners: bias -1.5 bpm, RMSE 9.2 bpm, MAPE 4.0%. 220 - age: bias -0.2, RMSE 9.8. HRmax was underestimated more often than overestimated. The authors' conclusion: use predictions only as a supplement, laboratory testing is preferable.
- Used for: Why max heart rate is estimated from your own peaks rather than an age formula
- How the app uses it: Evidence that age formulas carry an individual error of about 9 to 10 bpm for endurance athletes, even the best of them.
- Limits: Laboratory treadmill and cycle tests, mostly men; a peak from your own hard runs is not a laboratory maximum either, which is why the app shows the age formula next to it and lets you override the value.

## Valencia Marathon study 2025 (prediction equation)

See source (2025). Performance prediction equation for the Valencia Marathon based on time and pacing in the half marathon. Open-access journal (see link).

- Link: <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12856576/>
- Checked: **Abstract and summaries read; full text not yet checked**. Abstract only, and not the same paper as Latorre-Roman et al. 2025 (which is read in full and listed separately). Reported accuracy similar to the VDOT system but behaving differently by runner level. Full text still needed.
- Used for: Context for half-to-marathon prediction and for showing several methods side by side
- How the app uses it: Not a formula used by the app; informs the choice to show methods together instead of picking one.
- Limits: One race, one population. Authors and exact title not verified.

## Latorre-Roman et al. 2025

Latorre-Roman PA, Salas-Sanchez J, Aragon-Vela J (2025). Influence of sex, athletic category and athletic level on marathon pacing strategy: an analysis of the Trinidad Alfonso EDP Valencia Marathon from 2014 to 2023. European Journal of Sport Science 25:e12329. doi:10.1002/ejsc.12329

- Link: <https://doi.org/10.1002/ejsc.12329>
- Checked: **Full text read and checked against what the app does**. Full text read. 146,108 finishers analysed (official 5 km splits). Even pacing: 77.6% of women vs 74.3% of men; marathon time correlated with variability of speed (r = 0.551); a 'hit the wall' flag means a 30 or 35 km split more than 7.3% slower than the race's other splits. Even-pacing share fell from age category M55 (men) and F45 (women).
- Used for: Context for the marathon prediction caveats (slowing late in the race is common and varies with level)
- How the app uses it: Not a formula. It supports the warning that a marathon prediction from shorter efforts assumes you pace the race evenly.
- Limits: Official-timing data from one race; shows what runners did, not what a given runner should do.

## Wiecha et al. 2023 (PLOS ONE)

Wiecha S, Kasiak PS, Cieslinski I, Takken T, Palka T, Knechtle B, Nikolaidis PT, Malek LA, Postula M, Mamcarz A, Sliz D (2023). External validation of VO2max prediction models based on recreational and elite endurance athletes. PLOS ONE 18(1):e0280897. doi:10.1371/journal.pone.0280897

- Link: <https://doi.org/10.1371/journal.pone.0280897>
- Checked: **Full text read and checked against what the app does**. Full text read. 5,260 adult endurance athletes with laboratory-measured VO2max; 13 published prediction models tested. Agreement with measured values was low to moderate (best R2: 0.64 to 0.65 for cycling models, 0.26 to 0.30 for treadmill models); models under-estimated VO2max in younger, higher-trained athletes and over-estimated it in older, lower-trained ones.
- Used for: Why every VO2max number in the app is labelled an estimate for tracking, not a measurement
- How the app uses it: Not a formula. It is the evidence that general VO2max equations transfer poorly to endurance athletes.
- Limits: Tested equations that use age, sex, body size and activity level, not the race-time or heart-rate-ratio methods in this app.

## Hata et al. 2025 (HYPAC)

Hata K, Yanagiya T, Noro H, Suzuki Y (2025). Hata-Yanagiya physical activity calculation system: a novel global positioning system-based method for accurate estimation of oxygen consumption during walking and running. Frontiers in Sports and Active Living 6:1522214 (published 10 January 2025). doi:10.3389/fspor.2024.1522214

- Link: <https://doi.org/10.3389/fspor.2024.1522214>
- Checked: **Full text read and checked against what the app does**. Full text read. HYPAC estimates oxygen use DURING walking and running from GPS speed and slope: a regression on the Compendium of Physical Activities METs (threshold 8.69 km/h) times a slope-cost curve built from Minetti et al. 2002 data. Tested on 10 university students (5 runners) over 5 km against a portable gas analyser: relative error -0.03 (95% CI -0.14 to 0.08). The two ACSM equations are inconsistent at exactly 8 km/h on flat ground.
- Used for: Candidate cost-of-running model for a future submaximal VO2max method (NOT used in any calculation yet)
- How the app uses it: Not used. It estimates exercise oxygen use, not VO2max, and rests on only 10 young students, so it is too thinly validated to build a VO2max method on. It shares its slope data with the app's grade-adjusted pace (Minetti).
- Limits: 10 university students; one 5 km course; not endurance-trained athletes at race pace; authors call for larger validation.

## ACSM equation in athletes (Hippokratia)

See source. Indirect estimation of VO2max in athletes by ACSM's equation: valid or not?. Hippokratia.

- Link: <https://www.hippokratia.gr/?p=1728>
- Checked: **Known from secondary sources (summaries, vendor pages); the original was not read**. Search summary only: VO2max calculated with the ACSM running equation was 14.6% higher than measured in athletes aged 18-37 on the Bruce protocol.
- Used for: Why VO2max from the standard ACSM running-cost equation is treated with suspicion (NOT used in any calculation)
- How the app uses it: Not used; evidence for caution.
- Limits: Summary only; one protocol, one athlete group.

## Wiecha et al. 2023 (eLife)

Wiecha S, Kasiak PS, Szwed P, Kowalski T, Cieslinski I, Postula M, Klusiewicz A (2023). VO2max prediction based on submaximal cardiorespiratory relationships and body composition in male runners and cyclists: a population study. eLife 12:e86291. doi:10.7554/eLife.86291

- Link: <https://doi.org/10.7554/eLife.86291>
- Checked: **Full text read and checked against what the app does**. Full text read. 4,424 male endurance athletes (3,330 treadmill runners, 1,094 cyclists) with laboratory gas-exchange tests. Runner models: from oxygen uptake and speed at the respiratory compensation point R2 = 0.899, validation RMSE 2.08 ml/kg/min; from body fat and age only R2 = 0.35, RMSE 5.54. Every strong model needs measured oxygen uptake at a threshold (a laboratory gas analyser).
- Used for: Modern evidence on submaximal prediction (NOT used: it needs laboratory breathing data a watch does not record)
- How the app uses it: Not used. It shows what accuracy is possible with lab data (about +/-2 ml/kg/min) and how little age and body fat alone give (+/-5.5).
- Limits: Men only (too few women to model); laboratory treadmill protocol; internal validation only.

## Firstbeat white paper 2017

Firstbeat Technologies (2017). Automated fitness level (VO2max) estimation with heart rate and speed data. Company white paper (not peer reviewed).

- Link: <https://assets.firstbeat.com/firstbeat/uploads/2017/06/white_paper_VO2max_30.6.2017.pdf>
- Checked: **Known from secondary sources (summaries, vendor pages); the original was not read**. Known from search summaries: the approach behind Garmin's VO2max (heart rate and speed during runs); the company reports about 5% error in 79 runners. Company-sourced accuracy claims have not been independently verified.
- Used for: Context for how your watch's own VO2max number is produced (NOT used in any calculation)
- How the app uses it: Not used. Explains why the watch's value and this app's estimates can differ.
- Limits: Manufacturer document.

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

