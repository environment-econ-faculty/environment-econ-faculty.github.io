"""Fallback paper lists from OpenAlex AUTHOR records, for scholars whose homepage/CV could not be scraped.

Safety: an OpenAlex author is accepted only if its affiliations include the scholar's own university
(same-name authors elsewhere are rejected); if several author records match (split profiles), works are merged.
Writes data/papers_raw/<slug>.json in the scrape format, with notes saying the source.
Existing files are only overwritten if they have fewer papers than found here (unless --force).

Usage: python scripts/oa_author_fill.py slug1,slug2,...   [--force]
"""
import json, os, re, sys, unicodedata, urllib.parse, urllib.request, time
import csv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "papers_raw")
KEY = open(os.path.join(os.path.dirname(ROOT), "OpenAlex API key.txt"), encoding="utf-8").read().strip().split()[-1]
SRC = os.path.join(os.path.dirname(ROOT), "raw3", "round3_new.csv")
ALIAS = {"University of Tennessee, Knoxville": ["University of Tennessee"], "Louisiana State University": ["Louisiana State University"],
         "Virginia Tech": ["Virginia Tech", "Virginia Polytechnic Institute"], "Nanyang Technological University": ["Nanyang Technological University"],
         "North Carolina State University": ["North Carolina State University"]}


def get(url):
    sep = "&" if "?" in url else "?"
    for _ in range(3):
        try:
            with urllib.request.urlopen(url + sep + "api_key=" + KEY, timeout=40) as r:
                return json.load(r)
        except Exception as e:
            err = e
            time.sleep(2)
    raise err


def norm(s):
    return re.sub(r"[^a-z ]", " ", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


def clean_name(n):
    n = re.sub(r"\([^)]*\)", " ", n)
    return re.sub(r"\s+", " ", n.replace("Jr.", "")).strip()


def uni_match(names, uni):
    keys = [norm(k).strip() for k in ALIAS.get(uni, [uni])]
    return any(k and k in norm(n) for k in keys for n in names)


def inst_ok(author, uni):  # current (last known) institution must be the scholar's university
    return uni_match([i.get("display_name") for i in author.get("last_known_institutions") or []], uni)


ECON = ("Economics, Econometrics and Finance", "Social Sciences", "Business, Management and Accounting", "Decision Sciences")
BAD = ("Medicine", "Biochemistry", "Chemistry", "Mathematics", "Physics", "Materials", "Engineering", "Computer Science", "Nursing",
       "Pharmacology", "Immunology", "Neuroscience", "Health Professions", "Dentistry", "Veterinary", "Psychology", "Chemical Engineering")


def econ_author(a):
    return sum(1 for t in (a.get("topics") or [])[:10] if t["field"]["display_name"] in ECON) >= 1


STATUS = {"article": "已发表", "review": "已发表", "preprint": "工作论文", "report": "工作论文"}


def main():
    slugs = sys.argv[1].split(",")
    force = "--force" in sys.argv
    rows = {r["slug"]: r for r in csv.DictReader(open(SRC, encoding="utf-8-sig"))}
    for slug in slugs:
        r = rows[slug]
        name, uni = clean_name(r["name"]), r["university"]
        res = get("https://api.openalex.org/authors?per_page=25&search=" + urllib.parse.quote(name))["results"]
        sur = norm(name).split()[-1]
        cands = [a for a in res if inst_ok(a, uni) and sur in norm(a["display_name"]).split() and econ_author(a)]
        if not cands:
            print(f"{slug}: no OpenAlex author at {uni} (of {len(res)})")
            continue
        works, seen = [], set()
        for a in cands:
            aid = a["id"].rsplit("/", 1)[-1]
            cur = "*"
            while cur:
                j = get(f"https://api.openalex.org/works?filter=author.id:{aid}&per_page=200&cursor={cur}"
                        "&select=title,publication_year,type,primary_location,authorships,doi,primary_topic")
                for w in j["results"]:
                    t = (w.get("title") or "").strip()
                    k = norm(t)
                    if not t or k in seen or w.get("type") not in STATUS or len(t) < 15:
                        continue
                    fld = (((w.get("primary_topic") or {}).get("field") or {}).get("display_name") or "")
                    if fld.startswith(BAD):
                        continue
                    me = [x for x in w["authorships"] if x["author"]["id"] == a["id"]]
                    here = me and uni_match([i.get("display_name") for i in me[0].get("institutions") or []], uni)
                    if not here and fld not in ECON:
                        continue
                    if re.search(r"^(erratum|correction|front matter|back matter|table of contents|index)\b", k):
                        continue
                    seen.add(k)
                    src = (w.get("primary_location") or {}).get("source") or {}
                    works.append({"title": t, "authors": [x["author"]["display_name"] for x in w["authorships"]][:30],
                                  "year": w.get("publication_year"), "venue": src.get("display_name") or "",
                                  "status": STATUS[w["type"]], "url": w.get("doi") or "", "abstract": None})
                cur = j["meta"].get("next_cursor") if j["results"] else None
        works.sort(key=lambda p: -(p["year"] or 0))
        path = os.path.join(RAW, slug + ".json")
        old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
        if old and len(old.get("papers", [])) >= len(works) and not force:
            print(f"{slug}: kept existing ({len(old['papers'])} >= {len(works)})")
            continue
        out = {"slug": slug, "name": r["name"], "sources": [c["id"] for c in cands], "collected": "2026-11-06",
               "notes": f"Fallback: homepage/CV unavailable; list from OpenAlex author record(s) affiliated with {uni} "
                        f"({', '.join(c['display_name'] for c in cands)}). May include non-economics coauthored work; working papers mostly absent.",
               "papers": works}
        json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{slug}: {len(works)} papers from {len(cands)} author record(s)")


if __name__ == "__main__":
    main()
