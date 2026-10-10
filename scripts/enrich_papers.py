"""Enrich scraped paper lists (data/papers_raw/<slug>.json) with abstracts / DOIs from OpenAlex.

Paper lists come from scholars' own homepages and CVs (collected separately). Here we only look up
each paper by TITLE and accept a match when the normalized titles agree and one of the
authors shares the scholar's surname, so there is no author-disambiguation risk.
Also tags each paper as EEE-related by keywords.
Output: data/papers/<slug>.json (consumed by build.py). Raw files are never modified.

Usage: python scripts/enrich_papers.py [--only slug1,slug2] [--no-api] [--workers 8]
"""
import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "papers_raw")
OUT = os.path.join(ROOT, "data", "papers")
CACHE = os.path.join(ROOT, "data", "openalex_title_cache.json")
MAILTO = "zh443@cornell.edu"
STATUSES = ["已发表", "即将发表", "修改重投", "工作论文"]

EEE_RE = re.compile(
    r"\b(energy|electric\w*|power plant\w*|emission\w*|pollut\w*|climat\w*|carbon|co2|greenhouse|environment\w*|"
    r"renewable\w*|solar|wind (power|energy|farm\w*|turbine\w*)|oil\b|natural gas|gasoline|fuel\w*|coal|fracking|shale|"
    r"water|drought\w*|flood\w*|agricultur\w*|crop\w*|farm\w*|land use|deforest\w*|forest\w*|fisher\w*|"
    r"natural resource\w*|temperature\w*|heat\b|extreme weather|weather|air quality|ozone|pm2\.5|particulate|"
    r"sustainab\w*|natural disaster\w*|hurricane\w*|wildfire\w*|toxic|recycl\w*|electric vehicle\w*|"
    r"vehicle\w*|congestion|cap.and.trade|pigouvian|conservation|biodiversity|ecosystem\w*|methane|"
    r"decarboni\w*|green\b|smog|sanitation|cookstove\w*|irrigation|groundwater|mining|minerals?)\b", re.I)


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def surname(name):
    t = norm(name).split()
    while t and t[-1] in ("jr", "ii", "iii", "iv"):
        t.pop()
    return t[-1] if t else ""


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                return None
            time.sleep(2 * (i + 1))


def abstract_from(inv):
    if not inv:
        return ""
    pos = {}
    for w, idx in inv.items():
        for i in idx:
            pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))[:4000]


def lookup(title, sname, cache):
    key = norm(title)
    if key in cache:
        return cache[key]
    q = urllib.parse.urlencode({"search": title[:250], "per_page": 6, "mailto": MAILTO,
                                "select": "id,doi,title,publication_year,authorships,abstract_inverted_index"})
    d = get(f"https://api.openalex.org/works?{q}")
    best = None
    for w in (d or {}).get("results", []):
        wt = norm(w.get("title") or "")
        if not wt or not (wt == key or (len(key) > 30 and (wt.startswith(key) or key.startswith(wt)))):
            continue
        names = [surname((a.get("author") or {}).get("display_name", "")) for a in w.get("authorships") or []]
        if sname and sname not in names:
            continue
        ab = abstract_from(w.get("abstract_inverted_index"))
        cand = {"doi": (w.get("doi") or "").replace("https://doi.org/", ""), "abstract": ab, "oa": w["id"].split("/")[-1]}
        if not best or (ab and not best["abstract"]):
            best = cand
    cache[key] = best
    return best


def clean_abstract(a):
    a = (a or "").strip()
    a = re.sub(r"^(abstract|摘要)\s*[:：.]?\s*", "", a, flags=re.I)
    return a


def process(fn, use_api, cache):
    raw = json.load(open(os.path.join(RAW, fn), encoding="utf-8"))
    slug = fn[:-5]
    sname = surname(raw.get("name") or "")
    papers, seen = [], set()
    for p in raw.get("papers") or []:
        title = re.sub(r"\s+", " ", (p.get("title") or "")).strip().strip('"“”')
        if len(title) < 6:
            continue
        k = norm(title)
        if k in seen:
            continue
        seen.add(k)
        status = p.get("status") if p.get("status") in STATUSES else "工作论文"
        y = p.get("year")
        try:
            y = int(str(y)[:4]) if y else None
        except ValueError:
            y = None
        q = {"title": title, "authors": [a for a in (p.get("authors") or []) if a], "year": y,
             "venue": (p.get("venue") or "").strip(), "status": status, "url": p.get("url") or "",
             "abstract": clean_abstract(p.get("abstract")), "abs_src": "主页" if p.get("abstract") else ""}
        if use_api and (not q["abstract"] or "doi.org" not in q["url"]):
            m = lookup(title, sname, cache)
            if m:
                if not q["abstract"] and m["abstract"] and len(m["abstract"]) > 120:
                    q["abstract"] = m["abstract"]
                    q["abs_src"] = "OpenAlex"
                if m["doi"]:
                    q["doi"] = m["doi"]
                    if not q["url"]:
                        q["url"] = "https://doi.org/" + m["doi"]
        q["eee"] = bool(EEE_RE.search(title + " " + q["abstract"][:1500]))
        papers.append(q)
    order = {s: i for i, s in enumerate(STATUSES)}
    papers.sort(key=lambda p: (-(p["year"] or 0), order[p["status"]], p["title"]))
    out = {"slug": slug, "sources": raw.get("sources") or [], "collected": raw.get("collected"),
           "notes": raw.get("notes") or "", "papers": papers}
    with open(os.path.join(OUT, fn), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    return slug, len(papers), sum(1 for p in papers if p["abstract"])


def main():
    args = sys.argv[1:]
    only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else None
    use_api = "--no-api" not in args
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 10
    os.makedirs(OUT, exist_ok=True)
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    files = [f for f in sorted(os.listdir(RAW)) if f.endswith(".json") and (not only or f[:-5] in only)]
    if use_api:  # prefetch all needed title lookups in parallel (cache shared by process())
        todo = []
        for fn in files:
            raw = json.load(open(os.path.join(RAW, fn), encoding="utf-8"))
            sn = surname(raw.get("name") or "")
            for p in raw.get("papers") or []:
                t = re.sub(r"\s+", " ", (p.get("title") or "")).strip().strip('"“”')
                if len(t) >= 6 and norm(t) not in cache and (not p.get("abstract") or "doi.org" not in (p.get("url") or "")):
                    todo.append((t, sn))
        print(f"looking up {len(todo)} titles in OpenAlex ...", flush=True)
        with ThreadPoolExecutor(workers) as ex:
            for i, _ in enumerate(ex.map(lambda a: lookup(a[0], a[1], cache), todo)):
                if i and i % 500 == 0:
                    print(f"  {i}/{len(todo)}", flush=True)
    tot = [0, 0]
    with ThreadPoolExecutor(workers) as ex:
        for slug, n, na in ex.map(lambda f: process(f, use_api, cache), files):
            tot[0] += n
            tot[1] += na
            print(f"{slug}: {n} papers, {na} with abstract", flush=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    print(f"TOTAL {len(files)} scholars, {tot[0]} papers, {tot[1]} with abstract")


if __name__ == "__main__":
    main()
