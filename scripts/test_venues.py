"""clean_venue 的回归测试：python scripts/test_venues.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from venues import clean_venue  # noqa: E402

CASES = {
    "Science volume 343 issue 6696 (2024)": "Science",
    "Science, Vol. 357, Issue 6346": "Science",
    "Science 373 (2021) 850-852": "Science",
    "Nat Hum Behav 8, 2–3. https://doi.org/10.1038/s41562-023-01807-2": "Nat Hum Behav",
    "Journal of Financial Economics 142(2): 499-516": "Journal of Financial Economics",
    "Journal of Environmental Economics and Management, 33:186-195, June 1997": "Journal of Environmental Economics and Management",
    "Economic Inquiry, October 1993": "Economic Inquiry",
    "American Economic Journal: Economic Policy 9(4): 192-226": "American Economic Journal: Economic Policy",
    "Revise & Resubmit, Journal of Political Economy": "Journal of Political Economy",
    "Journal of the European Economic Association (conditionally accepted)": "Journal of the European Economic Association",
    "forthcoming Review of Economics and Statistics": "Review of Economics and Statistics",
    "NBER Working Paper No. 32830": "NBER Working Paper",
    "NBER Working Paper 33412, January 2025": "NBER Working Paper",
    "Working Paper, June 2022": "Working Paper",
    "Proceedings of the National Academy of Sciences 113(33): 9238-9243": "Proceedings of the National Academy of Sciences",
    "Population in the Human Sciences: Concepts, Models, Evidence edited by Philip Kreager, Bruce Winney, Stanley Ulijaszek":
        "Population in the Human Sciences: Concepts, Models, Evidence",
    "Caring and Exchange: The Pennsylvania State University Symposium on Family Issues, Urban Institute Press":
        "Caring and Exchange: The Pennsylvania State University Symposium on Family Issues",
    "L. P. Hansen and T. J. Sargent, Eds., In Rational Expectations Econometrics, (Boulder and Oxford: Westview Press 1991), 77-119":
        "Rational Expectations Econometrics",
    "in Susan M. Collins and Carol Graham (eds.) Global Labor Markets, Brookings Trade Forum, 2006, Washington, D.C.: Brookings Institution Press, 2006":
        "Global Labor Markets, Brookings Trade Forum",
    "Handbook of the Economics of Climate Change, Vol. 1 (eds. Barrage and Hsiang), Elsevier": "Handbook of the Economics of Climate Change",
    "Mani SS, Riang’a RM. Validation of cognitive tools in Kenya: findings from the LOSHAK pilot. BMC Public Health. 2025 Nov 17;25(1):4008. doi: 10.1186/x. PMID: 1.":
        "BMC Public Health",
    "Microeconomic Theory, ed. by Larry Samuelson, Kluwer-Nijhoff": "Microeconomic Theory",
    "In: The New Palgrave Dictionary of Economics, Steven Durlauf and Lawrence Blume (eds). Palgrave Macmillian Publishing (book chapter)":
        "The New Palgrave Dictionary of Economics",
    "Climate Change Mitigation: Policies and Lessons for Asia, 19-53 (book chapter)": "Climate Change Mitigation: Policies and Lessons for Asia",
    "Landscape Ecology 37 (10), 2551-2569": "Landscape Ecology",
    "Health & Place 13 (2007) 164–172": "Health & Place",
}

bad = 0
for v, want in CASES.items():
    got = clean_venue(v)
    if got != want:
        bad += 1
        print(f"FAIL {v[:70]!r}\n     got  {got!r}\n     want {want!r}")
print(f"{len(CASES) - bad}/{len(CASES)} passed")
