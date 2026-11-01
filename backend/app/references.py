"""The single bibliography for everything the app computes.

Mission: use your data to train smarter, and always show the math. That includes crediting the people
whose work the math comes from, and being honest about how well each source has been checked.

Every method, formula and claim in the app names one or more of these ids. The UI shows them as links to
a references page; docs/references.md is generated from this file (python -m app.references) and a test
fails if it drifts.
"""

from __future__ import annotations

from typing import Any

VERIFIED = {
    "full_text": "Full text read and checked against what the app does",
    "abstract": "Abstract and summaries read; full text not yet checked",
    "secondary": "Known from secondary sources (summaries, vendor pages); the original was not read",
    "documentation": "Vendor documentation read via search summaries",
}

REFERENCES: list[dict[str, Any]] = [
    {
        "id": "minetti2002", "short": "Minetti et al. 2002", "kind": "paper",
        "authors": "Minetti AE, Moia C, Roi GS, Susta D, Ferretti G",
        "year": 2002,
        "title": "Energy cost of walking and running at extreme uphill and downhill slopes",
        "venue": "Journal of Applied Physiology 93(3):1039-1046",
        "doi": "10.1152/japplphysiol.01177.2001", "url": "https://doi.org/10.1152/japplphysiol.01177.2001",
        "verified": "full_text",
        "verified_note": "Full text read (PDF supplied by the app's author). The polynomial below is the equation printed in "
                         "the legend of Fig. 1 (p. 1041); Table 2 (p. 1042) values match its predictions.",
        "used_for": ["Grade-adjusted pace (hills and trail runs)"],
        "how_used": "The energy cost of running on a slope i is Cr(i) = 155.4 i^5 - 30.4 i^4 - 43.3 i^3 + 46.3 i^2 + 19.5 i + 3.6 "
                    "(J per kg per metre, R2 = 0.999, slopes -0.45 to +0.45). The app multiplies each step's real distance by "
                    "Cr(i) / 3.6 to get flat-equivalent distance.",
        "limits": "Ten elite mountain-endurance men on a smooth treadmill. Measured level cost 3.40 +/- 0.24 versus 3.6 from the fit; "
                  "downhill running was about 40% cheaper than earlier data from sedentary people; the authors note rougher ground "
                  "raises the cost. Adjusted times are therefore approximate.",
    },
    {
        "id": "riegel1981", "short": "Riegel 1981", "kind": "paper",
        "authors": "Riegel PS", "year": 1981,
        "title": "Athletic records and human endurance",
        "venue": "American Scientist 69(3):285-290 (an earlier version, 'Time Predicting', appeared in Runner's World in 1977)",
        "doi": None, "url": "https://en.wikipedia.org/wiki/Peter_Riegel",
        "verified": "abstract",
        "verified_note": "Abstract and secondary summaries only. The commonly quoted form T2 = T1 x (D2/D1)^1.06 and the 3.5 to 230 minute "
                         "range come from those summaries, not the paper itself.",
        "used_for": ["Riegel power law (k = 1.06)", "Your fitted exponent", "Source-effort duration range (3.5 to 230 minutes)"],
        "how_used": "Time over a new distance = known time x (new distance / known distance)^k. The app uses k = 1.06 as the "
                    "textbook value and also fits k to the athlete's own efforts.",
        "limits": "Fitted to world-record-type data; the author's range was about 3.5 to 230 minutes. Many recreational runners "
                  "slow down more than k = 1.06 implies over long distances.",
    },
    {
        "id": "daniels1979", "short": "Daniels & Gilbert 1979", "kind": "book",
        "authors": "Daniels J, Gilbert J", "year": 1979,
        "title": "Oxygen Power: Performance Tables for Distance Runners (see also Daniels' Running Formula, Human Kinetics)",
        "venue": "Self-published, 1979", "doi": None, "url": "https://en.wikipedia.org/wiki/Jack_Daniels_(coach)",
        "verified": "secondary",
        "verified_note": "Equation constants confirmed from secondary sources (calculator and coaching pages). The app's implementation "
                         "reproduces the widely quoted value (a 20:00 5K gives a VDOT of 49.8); the book itself was not read.",
        "used_for": ["VDOT race-time prediction", "VDOT as a race-performance fitness index (VO2max section)"],
        "how_used": "oxygen cost = -4.60 + 0.182258 v + 0.000104 v^2 (v in m/min); fraction of VO2max held = 0.8 + 0.1894393 "
                    "e^(-0.012778 t) + 0.2989558 e^(-0.1932605 t) (t in minutes); VDOT = cost / fraction. Solved for the target distance.",
        "limits": "A 1979 model from competitive runners' performances. VDOT is a performance score, not a measured VO2max: it mixes aerobic "
                  "capacity with running economy, and one 2020 study of experienced marathoners found it related to a running-economy measure "
                  "but not to laboratory VO2max. It assumes the endurance base for the distance being predicted.",
    },
    {
        "id": "poole2016", "short": "Poole et al. 2016", "kind": "paper",
        "authors": "Poole DC, Burnley M, Vanhatalo A, Rossiter HB, Jones AM", "year": 2016,
        "title": "Critical power: an important fatigue threshold in exercise physiology",
        "venue": "Medicine & Science in Sports & Exercise 48(11):2320-2334",
        "doi": "10.1249/MSS.0000000000000939", "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC5070974",
        "verified": "abstract",
        "verified_note": "Abstract and search summaries read; full text (free on PubMed Central) not yet checked.",
        "used_for": ["Critical speed prediction"],
        "how_used": "Two-parameter model: distance = CS x time + D'. Fitted by least squares to the athlete's 2 to 40 minute efforts.",
        "limits": "The 2 to 40 minute window in which the app counts this method is the app's own conservative rule of thumb, "
                  "not a limit stated in the paper.",
    },
    {
        "id": "uth2004", "short": "Uth et al. 2004", "kind": "paper",
        "authors": "Uth N, Sorensen H, Overgaard K, Pedersen PK", "year": 2004,
        "title": "Estimation of VO2max from the ratio between HRmax and HRrest - the Heart Rate Ratio Method",
        "venue": "European Journal of Applied Physiology (2004)", "doi": None,
        "url": "https://www.springermedizin.de/estimation-of-vo2max-from-the-ratio-between-hrmax-and-hrrest-the/8478242",
        "verified": "abstract",
        "verified_note": "Abstract and search summaries read. Volume and page numbers are not given here because they were not verified.",
        "used_for": ["Heart rate ratio VO2max estimate"],
        "how_used": "VO2max (ml/kg/min) = 15.3 x HRmax / HRrest. The range shown uses the reported standard error of 4.7 ml/kg/min.",
        "limits": "The constant came from a subgroup of 10 well-trained men; the authors say other groups need direct validation. "
                  "The 4.7 error (about 7.8%) was with age-predicted HRmax.",
    },
    {
        "id": "molina2022", "short": "Molina-Garcia et al. 2022", "kind": "paper",
        "authors": "Molina-Garcia P, et al. (INTERLIVE Network)", "year": 2022,
        "title": "Validity of estimating the maximal oxygen consumption by consumer wearables: a systematic review with "
                 "meta-analysis and expert statement of the INTERLIVE Network",
        "venue": "Sports Medicine (2022)", "doi": None, "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9213394/",
        "verified": "abstract",
        "verified_note": "Abstract and search summaries read; full text not yet checked.",
        "used_for": ["Cautions on VO2max estimates (resting-data methods tend to read high; individual error stays large)"],
        "how_used": "Not a formula. It is why the app shows several VO2max methods with ranges and flags the resting-heart-rate method.",
        "limits": "A review of consumer wearables, not of the specific equations used here.",
    },
    {
        "id": "tanaka2001", "short": "Tanaka et al. 2001", "kind": "paper",
        "authors": "Tanaka H, Monahan KD, Seals DR", "year": 2001,
        "title": "Age-predicted maximal heart rate revisited",
        "venue": "Journal of the American College of Cardiology 37(1):153-156", "doi": None,
        "url": "https://pubmed.ncbi.nlm.nih.gov/11153730/",
        "verified": "abstract",
        "verified_note": "PubMed abstract read via search summaries (equation 208 - 0.7 x age; strong negative correlation of HRmax with age, "
                         "r = -0.90). Full text not read.",
        "used_for": ["Age-based max heart rate comparison"],
        "how_used": "HRmax = 208 - 0.7 x age, shown beside your own measured peaks as a sanity check, never used as the estimate.",
        "limits": "A population equation: individual error is large (see Kasiak et al. 2023).",
    },
    {
        "id": "kasiak2023", "short": "Kasiak et al. 2023", "kind": "paper",
        "authors": "Kasiak P, et al.", "year": 2023,
        "title": "Validity of the maximal heart rate prediction models among runners and cyclists",
        "venue": "Journal of Clinical Medicine (2023)", "doi": None, "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10146295/",
        "verified": "abstract",
        "verified_note": "Abstract and search summaries read (5,069 endurance athletes tested against maximal exercise tests; 9 of 13 "
                         "equations differed significantly from measured values; RMSE 9.1 to 10.5 bpm).",
        "used_for": ["Why max heart rate is estimated from your own peaks rather than an age formula"],
        "how_used": "Evidence that age formulas carry errors of roughly 9 to 10 bpm for individual endurance athletes.",
        "limits": "Laboratory tests; the authors recommend predictions only as a supplement to testing.",
    },
    {
        "id": "valencia2025", "short": "Valencia Marathon study 2025", "kind": "paper",
        "authors": "See source", "year": 2025,
        "title": "Performance prediction equation for the Valencia Marathon based on time and pacing in the half marathon",
        "venue": "Open-access journal (see link)", "doi": None, "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12856576/",
        "verified": "abstract",
        "verified_note": "Abstract only. Reported accuracy similar to the VDOT system but behaving differently by runner level.",
        "used_for": ["Context for half-to-marathon prediction and for showing several methods side by side"],
        "how_used": "Not a formula used by the app; informs the choice to show methods together instead of picking one.",
        "limits": "One race, one population.",
    },
    {
        "id": "frontiers2024_acsm", "short": "Frontiers 2024: ACSM equations", "kind": "paper",
        "authors": "See source", "year": 2024,
        "title": "Article on the accuracy of the ACSM metabolic equations for walking and running, proposing the HYPAC system "
                 "(Frontiers in Sports and Active Living, DOI 10.3389/fspor.2024.1522214; exact title not yet verified)",
        "venue": "Frontiers in Sports and Active Living (2024/2025)", "doi": "10.3389/fspor.2024.1522214",
        "url": "https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2024.1522214/full",
        "verified": "secondary",
        "verified_note": "Search summaries only (the publisher's site cannot be reached from the build environment): the ACSM walking and "
                         "running equations disagree at 8 km/h and often lack accuracy; the proposed system reported a relative error of -0.03 "
                         "against measured VO2.",
        "used_for": ["Candidate for a more accurate oxygen-cost-of-running equation (NOT used in any calculation yet)"],
        "how_used": "Not used. It is the reason the app does not build a VO2max method on the standard ACSM running equation.",
        "limits": "Not read in full; the claims above come from summaries.",
    },
    {
        "id": "acsm_athletes", "short": "ACSM equation in athletes (Hippokratia)", "kind": "paper",
        "authors": "See source", "year": None,
        "title": "Indirect estimation of VO2max in athletes by ACSM's equation: valid or not?",
        "venue": "Hippokratia", "doi": None, "url": "https://www.hippokratia.gr/?p=1728",
        "verified": "secondary",
        "verified_note": "Search summary only: VO2max calculated with the ACSM running equation was 14.6% higher than measured in athletes aged "
                         "18-37 on the Bruce protocol.",
        "used_for": ["Why VO2max from the standard ACSM running-cost equation is treated with suspicion (NOT used in any calculation)"],
        "how_used": "Not used; evidence for caution.", "limits": "Summary only; one protocol, one athlete group.",
    },
    {
        "id": "elife2023", "short": "eLife 2023: submaximal VO2max models", "kind": "paper",
        "authors": "See source", "year": 2023,
        "title": "VO2max prediction based on submaximal cardiorespiratory relationships and body composition in male runners and "
                 "cyclists: a population study",
        "venue": "eLife (2023)", "doi": None, "url": "https://elifesciences.org/articles/86291",
        "verified": "secondary",
        "verified_note": "Search summary only (publisher site unreachable from the build environment): regression models for runners and "
                         "cyclists with internal validation.",
        "used_for": ["Modern evidence on submaximal prediction (NOT used: it needs laboratory-grade breathing data a watch does not record)"],
        "how_used": "Not used.", "limits": "Males; needs measured cardiorespiratory variables and body composition.",
    },
    {
        "id": "firstbeat2017", "short": "Firstbeat white paper 2017", "kind": "analysis",
        "authors": "Firstbeat Technologies", "year": 2017,
        "title": "Automated fitness level (VO2max) estimation with heart rate and speed data",
        "venue": "Company white paper (not peer reviewed)", "doi": None,
        "url": "https://assets.firstbeat.com/firstbeat/uploads/2017/06/white_paper_VO2max_30.6.2017.pdf",
        "verified": "secondary",
        "verified_note": "Known from search summaries: the approach behind Garmin's VO2max (heart rate and speed during runs); the company reports "
                         "about 5% error in 79 runners. Company-sourced accuracy claims have not been independently verified.",
        "used_for": ["Context for how your watch's own VO2max number is produced (NOT used in any calculation)"],
        "how_used": "Not used. Explains why the watch's value and this app's estimates can differ.", "limits": "Manufacturer document.",
    },
    {
        "id": "fetch_everyone", "short": "Fetch Everyone analysis", "kind": "analysis",
        "authors": "Fetch Everyone (website)", "year": None,
        "title": "Marathon time prediction",
        "venue": "Website analysis, not peer reviewed", "doi": None,
        "url": "https://www.fetcheveryone.com/article/marathon-time-prediction-37",
        "verified": "secondary",
        "verified_note": "Read via search summaries. Reported: 1,071 marathoners with 5+ half and 5+ full marathons; fewer than 5% matched "
                         "k = 1.06 predictions; effective exponents were often nearer 1.15.",
        "used_for": ["Conservative scenario (Riegel k = 1.15)"],
        "how_used": "Only to set a deliberately cautious scenario beside the standard k = 1.06.",
        "limits": "Not peer reviewed; experienced runners, not typical recreational runners.",
    },
    {
        "id": "garmin_zones", "short": "Garmin manual: heart rate zones", "kind": "documentation",
        "authors": "Garmin Ltd.", "year": None,
        "title": "Setting your heart rate zones (owner's manual)",
        "venue": "Garmin documentation",
        "doi": None, "url": "https://www8.garmin.com/manuals/webhelp/instinct/EN-US/GUID-30C91919-943C-44E9-8048-901AC0881AEA.html",
        "verified": "documentation",
        "verified_note": "Read via search summaries: default zones come from your profile, can be shown as % of max heart rate or % of heart rate "
                         "reserve, and can be edited. The specific default percentages could NOT be confirmed.",
        "used_for": ["Why the app's zone bands are labelled an estimate"],
        "how_used": "The app draws zones using a common five-zone convention (50/60/70/80/90% of max heart rate). It does not claim "
                    "these are your Garmin's boundaries; reading your real ones is on the roadmap.",
        "limits": "Your watch's zones may differ.",
    },
]

_BY_ID = {r["id"]: r for r in REFERENCES}


def get(ids: list[str]) -> list[dict[str, Any]]:
    missing = [i for i in ids if i not in _BY_ID]
    if missing:
        raise KeyError(f"unknown reference id(s): {missing}")
    return [{**_BY_ID[i], "verified_label": VERIFIED[_BY_ID[i]["verified"]]} for i in ids]


def all_references() -> list[dict[str, Any]]:
    return get([r["id"] for r in REFERENCES])


def format_citation(r: dict[str, Any]) -> str:
    year = f" ({r['year']})" if r.get("year") else ""
    doi = f" doi:{r['doi']}" if r.get("doi") else ""
    return f"{r['authors']}{year}. {r['title']}. {r['venue']}.{doi}"


def to_markdown() -> str:
    lines = [
        "# References and credits", "",
        "<!-- Generated from backend/app/references.py by `python -m app.references`. Do not edit by hand. -->", "",
        "Mission: use your data to train smarter, and always show the math. That includes crediting the people whose "
        "work the math comes from, and being honest about how well each source has been checked. Every method in the "
        "app names its sources, and the app's References page shows the same list.", "",
        "**How well each source was checked**", "",
        *[f"- **{k.replace('_', ' ')}**: {v}" for k, v in VERIFIED.items()], "",
    ]
    for r in all_references():
        lines += [f"## {r['short']}", "", format_citation(r), ""]
        lines += [f"- Link: <{r['url']}>"] if r.get("url") else []
        lines += [f"- Checked: **{r['verified_label']}**. {r['verified_note']}",
                  f"- Used for: {'; '.join(r['used_for'])}",
                  f"- How the app uses it: {r['how_used']}",
                  f"- Limits: {r['limits']}", ""]
    lines += [
        "## Software and data credits", "",
        "- Garmin Connect Personal API; endpoint paths follow Garmin's published Python client "
        "(<https://github.com/garmin/connect-personal-api-python>, Apache-2.0). No code was copied.",
        "- Map tiles and data: (c) OpenStreetMap contributors (<https://www.openstreetmap.org/copyright>), shown on every map.",
        "- Libraries: see [licenses](licenses.md) (Leaflet, uPlot, FastAPI, React, Docling and others).", "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(to_markdown())
