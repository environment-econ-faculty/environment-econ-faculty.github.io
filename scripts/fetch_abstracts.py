"""重新获取能源/环境类论文（eee=True）的英文摘要，纯脚本、不用模型。

流程（见 ABSTRACT_PLAN.md）：
  1. 收集 DOI：论文自带 doi > data/doi_fill.json > 从链接解析（doi.org、NBER、SSRN、nature.com、各出版社 /doi/ 路径）。
  2. 有 DOI 的：OpenAlex 按 DOI 批量查（每次 50 个），并查 Crossref 摘要；返回标题须与本地标题一致，防止 DOI 配错。
  3. 无 DOI（或 DOI 查不到）的：OpenAlex 标题搜索，规范化标题一致 + 作者姓氏吻合才采用。
  4. 清洗与校验：去 JATS/HTML 标签和开头的 "Abstract"；长度 250–6000 字符；剔除版权页/登录页文字、非英文。
  5. 选用：Crossref（出版社提供）> OpenAlex；都没有则保留主页抄录的旧摘要（通过校验时），旧的 OpenAlex 标题匹配摘要作废。
输出 data/abstracts.json：{title_key: {"en", "src", "doi"}}；data/abstracts_log.json 记录每篇的处理结果。

Usage: python scripts/fetch_abstracts.py [--workers 6] [--limit N] [--refresh]
API key 读自 ../OpenAlex API key.txt 或环境变量 OPENALEX_API_KEY。
"""
import glob, html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, LOG = os.path.join(ROOT, "data", "abstracts.json"), os.path.join(ROOT, "data", "abstracts_log.json")
CACHE = os.path.join(ROOT, "data", "abstracts_cache.json")
UA = "EEEFacultyDirectory/1.0 (mailto:zh443@cornell.edu)"
KEYFILE = os.path.join(os.path.dirname(ROOT), "OpenAlex API key.txt")
OA_KEY = os.environ.get("OPENALEX_API_KEY") or (open(KEYFILE).read().strip() if os.path.exists(KEYFILE) else "")

BAD = re.compile(r"jstor|purchase|log ?in|sign ?in|cookies?\b|this content downloaded|subscribe|access to this|"
                 r"full[- ]text|preview|copyright clearance|all rights reserved\.?$|^no abstract|abstract not available|"
                 r"terms and conditions|cambridge core|click here", re.I)
EN_WORDS = re.compile(r"\b(the|of|and|in|to|we|that|this|for|is|on|with)\b", re.I)


def norm(s):
    s = unicodedata.normalize("NFKD", html.unescape(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def key(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:80]


def surname(n):
    t = norm(n).split()
    while t and t[-1] in ("jr", "ii", "iii", "iv"):
        t.pop()
    return t[-1] if t else ""


def same_title(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a == b or (len(a) > 30 and (a.startswith(b) or b.startswith(a)) and min(len(a), len(b)) > 25):
        return True
    ta, tb = set(a.split()), set(b.split())  # 小差异（副标题标点、冠词）容忍
    return len(ta & tb) / max(len(ta | tb), 1) >= 0.85


def doi_from(p, fill):
    d = p.get("doi") or fill.get(key(p.get("title")))
    if d:
        return d.lower()
    u = urllib.parse.unquote(p.get("url") or "")
    m = re.search(r"nber\.org/(?:system/files/working_papers/|papers/)(w\d+)", u)
    if m:
        return "10.3386/" + m.group(1)
    m = re.search(r"ssrn\.com/.*abstract(?:_id)?=(\d+)", u)
    if m:
        return "10.2139/ssrn." + m.group(1)
    m = re.search(r"nature\.com/articles/(s\d{5}-\d{3}-\d{5}-\w)", u)
    if m:
        return "10.1038/" + m.group(1)
    m = re.search(r"aeaweb\.org/articles\?id=(10\.\d{4,9}/[^&#\s]+)", u)
    if m:
        return m.group(1).lower()
    m = re.search(r"(10\.\d{4,9}/[^\s?#&\"']+)", u)
    if m and "sciencedirect" not in u:
        d = re.sub(r"(/(full|abstract|pdf|epdf|meta))+$", "", m.group(1).rstrip(".)/"), flags=re.I)
        return re.sub(r"\.pdf$", "", d, flags=re.I).lower()
    return ""


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            time.sleep(2 * (i + 1) if e.code != 429 else 10 * (i + 1))
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
    return None


def oa_url(path, **q):
    if OA_KEY:
        q["api_key"] = OA_KEY
    return "https://api.openalex.org/" + path + "?" + urllib.parse.urlencode(q)


def inv_to_text(inv):
    if not inv:
        return ""
    pos = {}
    for w, idx in inv.items():
        for i in idx:
            pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))


def clean(t):
    t = html.unescape(t or "")
    t = re.sub(r"<jats:title>.*?</jats:title>", " ", t, flags=re.S | re.I)
    t = re.sub(r"</?(jats:)?p[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    t = re.sub(r"^(abstract|summary|a b s t r a c t)\s*[:.\-—]?\s*", "", t, flags=re.I)
    return t.strip()


def valid(t, title=""):
    if not (250 <= len(t) <= 6000):
        return False
    head = t[:300]
    if BAD.search(head) or BAD.search(t[-120:]):
        return False
    if len(EN_WORDS.findall(t)) < len(t.split()) * 0.12:  # 非英文或乱码
        return False
    if title and norm(t).startswith(norm(title)) and len(t) < len(title) + 300:
        return False
    return True


def score(t):  # 偏好完整（以句号等收尾）的版本
    return (t.rstrip()[-1:] in ".?!)\"'”%", len(t))


def crossref_abs(doi):
    r = get("https://api.crossref.org/works/" + urllib.parse.quote(doi), tries=3)
    if not r:
        return "", ""
    m = r.get("message", {})
    return clean(m.get("abstract", "")), (m.get("title") or [""])[0]


SEL = "id,doi,title,authorships,abstract_inverted_index,publication_year"


def oa_by_dois(dois):
    out = {}
    for i in range(0, len(dois), 50):
        chunk = dois[i:i + 50]
        r = get(oa_url("works", filter="doi:" + "|".join(chunk), select=SEL, **{"per-page": 50}))
        for w in (r or {}).get("results", []):
            d = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            out[d] = w
    return out


def oa_title_search(p):
    t = re.sub(r"[,:;|!?()\[\]\"]", " ", p["title"])[:250]
    r = get(oa_url("works", search=t, select=SEL, **{"per-page": 8}))
    sn = {surname(a) for a in p.get("authors") or [] if a}
    hits = []
    for w in (r or {}).get("results", []):
        if not same_title(w.get("title"), p["title"]):
            continue
        ws = {surname(a.get("author", {}).get("display_name", "")) for a in w.get("authorships") or []}
        if sn and ws and not (sn & ws):
            continue
        hits.append(w)
    return hits


def process(item):
    k, p, doi, cache = item
    if k in cache:
        return k, cache[k]
    res = {"doi": doi, "cands": []}
    title = p["title"]
    if doi:
        w = p.get("_oa")
        if w and not same_title(w.get("title"), title):
            res["doi_mismatch"] = w.get("title")
            w = None
        if w:
            res["cands"].append(["OpenAlex", clean(inv_to_text(w.get("abstract_inverted_index")))])
        ca, ct = crossref_abs(doi)
        if ca and (not ct or same_title(ct, title)):
            res["cands"].append(["Crossref", ca])
    if not any(valid(c[1], title) for c in res["cands"]):
        for w in oa_title_search(p):
            d = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            res["cands"].append(["OpenAlex", clean(inv_to_text(w.get("abstract_inverted_index")))])
            if d and not res["doi"]:
                res["doi"] = d
            if d and d != doi:
                ca, ct = crossref_abs(d)
                if ca and (not ct or same_title(ct, title)):
                    res["cands"].append(["Crossref", ca])
    return k, res


def main():
    a = sys.argv[1:]
    workers = int(a[a.index("--workers") + 1]) if "--workers" in a else 6
    limit = int(a[a.index("--limit") + 1]) if "--limit" in a else 0
    if not OA_KEY:
        print("WARNING: no OpenAlex key")
    fp = os.path.join(ROOT, "data", "doi_fill.json")
    fill = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {}
    cache = {} if "--refresh" in a or not os.path.exists(CACHE) else json.load(open(CACHE, encoding="utf-8"))
    U = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "papers", "*.json"))):
        for p in json.load(open(f, encoding="utf-8")).get("papers", []):
            if p.get("eee") and len(norm(p.get("title"))) >= 10:
                k = key(p["title"])
                if k not in U or (p.get("abstract") and not U[k].get("abstract")):
                    U[k] = p
    items = list(U.items())[:limit] if limit else list(U.items())
    dois = {k: doi_from(p, fill) for k, p in items}
    need = sorted({d for k, d in dois.items() if d and k not in cache})
    print(f"{len(items)} EEE papers; {sum(1 for d in dois.values() if d)} with DOI; querying OpenAlex for {len(need)} DOIs", flush=True)
    oa = oa_by_dois(need)
    print(f"  OpenAlex DOI hits: {len(oa)}", flush=True)
    todo = []
    for k, p in items:
        q = dict(p)
        q["_oa"] = oa.get(dois[k])
        todo.append((k, q, dois[k], cache))
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for n, (k, res) in enumerate(ex.map(process, todo), 1):
            cache[k] = res
            if n % 200 == 0:
                print(f"  {n}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    out, log, stats = {}, {}, {}
    for k, p in items:
        res = cache.get(k, {})
        good = [c for c in res.get("cands", []) if valid(c[1], p["title"])]
        good.sort(key=lambda c: (score(c[1])[0], c[0] == "Crossref", score(c[1])[1]), reverse=True)
        old = clean(p.get("abstract", ""))
        if good:
            src, en = good[0]
        elif old and p.get("abs_src") != "OpenAlex" and valid(old, p["title"]):
            src, en = "主页", old
        else:
            src, en = "", ""
        stats[src or "无"] = stats.get(src or "无", 0) + 1
        log[k] = {"title": p["title"], "doi": res.get("doi", ""), "src": src, "n_cands": len(res.get("cands", [])),
                  "old_src": p.get("abs_src", "") if old else "", "doi_mismatch": res.get("doi_mismatch", "")}
        if en:
            out[k] = {"en": en, "src": src, "doi": res.get("doi", "")}
        elif res.get("doi"):
            out[k] = {"en": "", "src": "", "doi": res["doi"]}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("sources:", stats, f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
