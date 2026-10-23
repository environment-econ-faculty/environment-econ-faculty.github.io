"""为没有链接的论文查找 DOI（Crossref 免费接口，不用模型、不需要 key）。

读 data/papers/*.json，对缺 url 的论文按标题 + 第一作者查询 Crossref，
标题规范化后一致且有作者姓氏吻合才采用。结果写入 data/doi_fill.json（key = 标题前 80 个字母数字），
查不到的记入 data/doi_miss.json，重跑时跳过；请求失败的不记录，下次重试。

Usage: python scripts/resolve_dois.py [--workers 8] [--limit N]
"""
import glob, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILL, MISS = os.path.join(ROOT, "data", "doi_fill.json"), os.path.join(ROOT, "data", "doi_miss.json")
UA = "EEEFacultyDirectory/1.0 (mailto:zh443@cornell.edu)"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def key(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())[:80]


def surname(n):
    t = norm(n).split()
    while t and t[-1] in ("jr", "ii", "iii", "iv"):
        t.pop()
    return t[-1] if t else ""


def query(p):
    title, authors = p["title"], p.get("authors") or []
    sn = {surname(a) for a in authors if a}
    q = {"query.bibliographic": title[:300], "rows": 5, "select": "DOI,title,author"}
    if authors:
        q["query.author"] = authors[0][:80]
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(q)
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=40) as r:
                items = json.load(r)["message"]["items"]
            break
        except Exception:  # noqa: BLE001
            time.sleep(3 * (i + 1))
    else:
        return None
    k = norm(title)
    for it in items:
        ct = norm((it.get("title") or [""])[0])
        if not ct or not (ct == k or (len(k) > 40 and (ct.startswith(k) or k.startswith(ct)))):
            continue
        cs = {surname(f"{a.get('given', '')} {a.get('family', '')}") for a in it.get("author") or []}
        if sn and cs and not (sn & cs):
            continue
        return it["DOI"]
    return ""


def main():
    a = sys.argv[1:]
    workers = int(a[a.index("--workers") + 1]) if "--workers" in a else 8
    limit = int(a[a.index("--limit") + 1]) if "--limit" in a else 0
    fill = json.load(open(FILL, encoding="utf-8")) if os.path.exists(FILL) else {}
    miss = set(json.load(open(MISS, encoding="utf-8"))) if os.path.exists(MISS) else set()
    todo, seen = [], set()
    for f in glob.glob(os.path.join(ROOT, "data", "papers", "*.json")):
        for p in json.load(open(f, encoding="utf-8")).get("papers", []):
            k = key(p.get("title"))
            if p.get("url") or p.get("doi") or len(norm(p.get("title"))) < 15 or k in fill or k in miss or k in seen:
                continue
            seen.add(k)
            todo.append(p)
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} papers to resolve", flush=True)
    t0, found = time.time(), 0
    with ThreadPoolExecutor(workers) as ex:
        for n, (p, d) in enumerate(zip(todo, ex.map(query, todo)), 1):
            if d:
                fill[key(p["title"])] = d
                found += 1
            elif d == "":
                miss.add(key(p["title"]))
            if n % 500 == 0:
                print(f"  {n}/{len(todo)} found {found} ({time.time() - t0:.0f}s)", flush=True)
                json.dump(fill, open(FILL, "w", encoding="utf-8"))
    json.dump(fill, open(FILL, "w", encoding="utf-8"))
    json.dump(sorted(miss), open(MISS, "w", encoding="utf-8"))
    print(f"done: {found}/{len(todo)} resolved in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
