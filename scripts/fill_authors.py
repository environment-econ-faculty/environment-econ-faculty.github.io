"""把论文作者列表中的简写名（如 "S. Li"）补成全名（如 "Siyuan Li"），纯脚本、不用模型。

来源（都免费）：
  1. 有 DOI 的（论文自带 / doi_fill.json / abstracts.json / 链接里解析）：Crossref 作者 given+family，
     OpenAlex 单篇（singleton）authorships 的 raw_author_name / display_name。远端标题须与本地一致，防止 DOI 配错。
  2. 无 DOI 的：Crossref 书目检索（标题 + 第一作者），标题一致且作者姓氏吻合才采用。
  3. 远端仍是简写或查不到时：若简写名与该论文所属的本库学者姓 + 首字母一致（且列表里只有这一个），用学者全名。
匹配规则：按姓氏对齐；首字母一致、简写里的中间名首字母（如有）也一致；同姓多人时按作者顺序对齐，仍有歧义则不改。
输出 data/author_fill.json：{title_key: {原简写名: 全名}}，build.py 应用；data/author_fill_log.json 记录未解决的。

Usage: python scripts/fill_authors.py [--workers 6] [--limit N] [--oa-search N [--nokey]]
  --oa-search N：对上轮仍未解决的论文再做 OpenAlex 标题搜索（最多 N 篇；免费 key $1/天≈1000 次，无 key 每 IP $0.1/天≈100 次）
"""
import difflib, glob, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_abstracts as fa  # noqa: E402  复用 norm / same_title / get / oa_url / doi_from

ROOT = fa.ROOT
OUT, LOG = os.path.join(ROOT, "data", "author_fill.json"), os.path.join(ROOT, "data", "author_fill_log.json")
CACHE = os.path.join(ROOT, "data", "author_cache.json")
SUFFIX = {"jr", "jr.", "ii", "iii", "iv"}
COMMON = set("li wang zhang liu chen yang zhao huang zhou wu xu sun hu zhu gao lin he guo ma luo liang song zheng xie han tang feng "
             "deng cao peng zeng xiao tian dong pan yuan cai jiang yu du ye cheng wei su lu ding shen ren yao lu jin fu "
             "kim lee park choi jung kang cho yoon jang lim nguyen tran le pham smith johnson brown jones miller davis "
             "wilson anderson taylor thomas moore martin jackson white harris clark lewis young walker hall allen king "
             "wright scott green baker adams nelson hill campbell mitchell roberts carter phillips evans turner parker "
             "collins edwards stewart morris murphy cook rogers morgan cooper peterson bailey reed kelly howard ward "
             "cox richardson wood watson brooks bennett gray james hughes price sanders myers long ross foster shah "
             "patel singh kumar gupta sharma das".split())


def toks(name):
    name = re.sub(r"[´`¨]", "", name or "")  # "Yu´nez" 这类抄录符号
    t = name.replace(".", ". ").split()
    while t and t[-1].lower().rstrip(",") in SUFFIX:
        t.pop()
    return t


def is_abbr(name):
    t = toks(name)
    return len(t) >= 2 and all(re.fullmatch(r"[A-Z]\.?(-[A-Z]\.?)?", x) for x in t[:-1])


def surname(name):
    t = toks(name)
    return fa.norm(t[-1]) if t else ""


def initials(name):
    """简写名的首字母序列，如 'J. H. Stock' -> ['j','h']；'J.-P. Smith' -> ['j','p']"""
    return [c.lower() for x in toks(name)[:-1] for c in re.findall(r"[A-Z]", x)]


def given_parts(full):
    t = toks(full)[:-1]
    return [fa.norm(x) for x in t if fa.norm(x)]


def full_ok(full):
    """远端名字是否真的是全名（名至少有一个 ≥2 字母的词）"""
    return any(len(re.sub(r"[^A-Za-z]", "", x)) >= 2 for x in toks(full)[:-1])


def compatible(abbr, full):
    if surname(abbr) != surname(full):
        return False
    ini, g = initials(abbr), given_parts(full)
    if not ini or not g:
        return False
    gi = [c for x in g for c in [x[0]]]  # 每个名词的首字母
    hy = [p[0] for x in toks(full)[:-1] for p in re.split(r"-", fa.norm(x).replace(" ", "-")) if p]
    if ini[0] != gi[0]:
        return False
    if len(ini) > 1:  # 中间名首字母须吻合（允许连字符名 Jean-Pierre -> J.-P.）
        return ini == gi[:len(ini)] or ini == hy[:len(ini)]
    return True


def lenient(abbr, full):
    """宽松匹配：姓氏允许小拼写差异（MacLaughlan/MacLachlan、Goebel/Göbel），
    首字母可对应任一名（M. Massey = D. Matthew Massey），中间名只在双方都有时比对。"""
    a, b = surname(abbr), surname(full)
    if not a or not b:
        return False
    if a != b and not (a[0] == b[0] and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8
                       or a.replace("oe", "o") == b.replace("oe", "o")):
        return False
    ini, g = initials(abbr), [x[0] for x in given_parts(full)]
    return bool(ini and g) and ini[0] in g


def tidy(full):
    full = re.sub(r"\s+", " ", full).strip()
    m = re.fullmatch(r"([A-Z][a-z]{2,})\. ([A-Z][a-z]+)", full)  # "Bushnell. James"
    if m:
        full = f"{m.group(2)} {m.group(1)}"
    if full.count(",") == 1:  # "Hughes, Jonathan" -> "Jonathan Hughes"
        fam, giv = [x.strip() for x in full.split(",")]
        full = f"{giv} {fam}".strip()
    if full.isupper() or full.islower():
        full = " ".join(w.capitalize() if len(w) > 2 else w.title() for w in full.split())
    return full


def remote_by_doi(doi):
    out = {"title": "", "names": []}
    r = fa.get("https://api.crossref.org/works/" + urllib.parse.quote(doi), tries=3)
    m = (r or {}).get("message", {})
    if m:
        out["title"] = (m.get("title") or [""])[0]
        out["names"].append([tidy(f"{a.get('given', '')} {a.get('family', '')}") for a in m.get("author") or [] if a.get("family")])
    w = fa.get(fa.oa_url("works/doi:" + urllib.parse.quote(doi, safe="/:"), select="title,authorships"), tries=3)
    if w:
        out["title"] = out["title"] or w.get("title") or ""
        aus = w.get("authorships") or []
        out["names"].append([tidy(a.get("raw_author_name") or "") for a in aus if a.get("raw_author_name")])
        out["names"].append([tidy((a.get("author") or {}).get("display_name") or "") for a in aus])
    return out


def remote_by_title(p):
    for d, _ in fa.crossref_title_dois(p)[:1]:
        r = remote_by_doi(d)
        r["doi"] = d
        return r
    return None


def resolve(local, remote_lists):
    """对每个简写名，在远端名单中找唯一相容的全名。"""
    fix = {}
    n = len(local)
    for i, a in enumerate(local):
        if not is_abbr(a):
            continue
        for names in remote_lists:
            names = [tidy(x) for x in names]
            c = [(j, f) for j, f in enumerate(names) if full_ok(f) and compatible(a, f)]
            if len(c) > 1:  # 同姓同首字母多人：按位置对齐
                c = [(j, f) for j, f in c if len(names) == n and j == i]
            if len(c) == 1:
                fix[a] = c[0][1]
                break
        if a in fix:
            continue
        for names in remote_lists:  # 第二轮：宽松匹配，仍须唯一，且远端名单里没有同姓的简写本人
            names = [tidy(x) for x in names]
            c = {f for f in names if full_ok(f) and lenient(a, f)}
            if len(c) == 1:
                fix[a] = c.pop()
                break
    return fix


def process(item):
    k, p, doi, cache = item
    if k in cache:
        return k, cache[k]
    r = remote_by_doi(doi) if doi else None
    if r and r["title"] and not fa.same_title(r["title"], p["title"]):
        r = None  # DOI 配错
    if not r or not any(r["names"]):
        r = remote_by_title(p)
    return k, r or {"title": "", "names": []}


def oa_search_pass(log, cache, U, nokey, cap):
    """对仍有未解决简写名的论文做 OpenAlex 标题搜索（付费 $0.001/次，用尽即停）。EEE 论文优先。"""
    ks = sorted((k for k in log if not cache.get(k, {}).get("oa_searched")), key=lambda k: not U[k].get("eee"))[:cap]
    done = 0
    for k in ks:
        p = U[k]
        q = {"search": re.sub(r"[,:;|!?()\[\]\"]", " ", p["title"])[:250], "select": "title,authorships", "per-page": 5}
        if not nokey and fa.OA_KEY:
            q["api_key"] = fa.OA_KEY
        try:
            with urllib.request.urlopen(urllib.request.Request("https://api.openalex.org/works?" + urllib.parse.urlencode(q),
                                                               headers={"User-Agent": fa.UA}), timeout=40) as r:
                res = json.load(r).get("results", [])
        except urllib.error.HTTPError as e:
            print("  stop:", e.code, f"after {done} searches")
            break
        except Exception:  # noqa: BLE001
            continue
        sn = {surname(x) for x in p.get("authors") or []}
        for w in res:
            names = [tidy((a.get("author") or {}).get("display_name") or "") for a in w.get("authorships") or []]
            raw = [tidy(a.get("raw_author_name") or "") for a in w.get("authorships") or []]
            if fa.same_title(w.get("title"), p["title"]) and sn & {surname(x) for x in names}:
                cache.setdefault(k, {"title": "", "names": []})["names"] += [raw, names]
                break
        cache.setdefault(k, {"title": "", "names": []})["oa_searched"] = True
        done += 1
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"  OpenAlex title search: {done} papers")


def main():
    a = sys.argv[1:]
    workers = int(a[a.index("--workers") + 1]) if "--workers" in a else 6
    limit = int(a[a.index("--limit") + 1]) if "--limit" in a else 0
    fill = json.load(open(os.path.join(ROOT, "data", "doi_fill.json"), encoding="utf-8"))
    absj = json.load(open(os.path.join(ROOT, "data", "abstracts.json"), encoding="utf-8"))
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    scholars = {}  # slug -> 全名（来自 data/scholars/*.md 的「姓名」）
    for f in glob.glob(os.path.join(ROOT, "data", "scholars", "*.md")):
        m = re.search(r"^姓名\s*[:：]\s*(.+)$", open(f, encoding="utf-8").read(), re.M)
        if m:
            scholars[os.path.basename(f)[:-3]] = m.group(1).strip()
    U, owners = {}, {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "papers", "*.json"))):
        slug = os.path.basename(f)[:-5]
        for p in json.load(open(f, encoding="utf-8")).get("papers", []):
            k = fa.key(p.get("title"))
            if len(fa.norm(p.get("title"))) < 10:
                continue
            owners.setdefault(k, set()).add(slug)
            if any(is_abbr(x) for x in p.get("authors") or []):
                U.setdefault(k, p)
    items = list(U.items())[:limit] if limit else list(U.items())
    todo = []
    for k, p in items:
        d = p.get("doi") or fill.get(k) or absj.get(k, {}).get("doi") or fa.doi_from(p, {})
        todo.append((k, p, (d or "").lower(), cache))
    print(f"{len(todo)} papers with abbreviated authors; {sum(1 for t in todo if t[2])} with DOI", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for n, (k, r) in enumerate(ex.map(process, todo), 1):
            cache[k] = r
            if n % 200 == 0:
                print(f"  {n}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)
                json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    if "--oa-search" in a:  # 需要上一轮的 author_fill_log.json
        prev = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}
        cap = int(a[a.index("--oa-search") + 1])
        oa_search_pass({k: v for k, v in prev.items() if k in U}, cache, U, "--nokey" in a, cap)

    out, log, res, st = {}, {}, {}, {"remote": 0, "scholar": 0, "inferred": 0, "unresolved": 0}
    for k, p in items:
        local = p.get("authors") or []
        fix = resolve(local, cache.get(k, {}).get("names", []))
        st["remote"] += len(fix)
        own = [scholars[s] for s in owners.get(k, ()) if s in scholars]
        for a in local:
            if is_abbr(a) and a not in fix:
                c = [s for s in own if compatible(a, s)]
                if len(c) == 1 and sum(1 for b in local if is_abbr(b) and compatible(b, c[0])) == 1:
                    fix[a] = c[0]
                    st["scholar"] += 1
        res[k] = fix
    # 4. 同一学者名下其他论文已确认的全名（工作论文 / 发表版常只有一版能查到）。
    #    常见姓氏须两篇论文还有共同合作者才借用，且该简写在此学者名下只对应一个全名。
    by_owner = {}
    for k, fix in res.items():
        for s in owners.get(k, ()):
            for a, f in fix.items():
                by_owner.setdefault((s, a), {}).setdefault(f, set()).add(k)
    for k, p in items:
        local, fix = p.get("authors") or [], res[k]
        sn = {surname(x) for x in local} - {surname(scholars.get(s, "")) for s in owners.get(k, ())}  # 不算本库学者自己
        for a in local:
            if not is_abbr(a) or a in fix:
                continue
            c = {}
            for s in owners.get(k, ()):
                for f, ks in by_owner.get((s, a), {}).items():
                    c.setdefault(f, set()).update(ks)
            if len(c) != 1:
                continue
            f, ks = next(iter(c.items()))
            shared = any(len(sn & {surname(x) for x in U[k2].get("authors") or []} - {surname(a)}) >= 1 for k2 in ks)
            if surname(a) not in COMMON or shared:
                fix[a] = f
                st["inferred"] += 1
    for k, p in items:
        local, fix = p.get("authors") or [], res[k]
        left = [a for a in local if is_abbr(a) and a not in fix]
        st["unresolved"] += len(left)
        if fix:
            out[k] = fix
        if left:
            log[k] = {"title": p["title"], "authors": local, "unresolved": left, "owners": sorted(owners.get(k, ())),
                      "remote": cache.get(k, {}).get("names", [])[:1]}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("names fixed:", st, f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
