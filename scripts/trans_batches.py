"""中文摘要翻译的批次管理。

  python scripts/trans_batches.py make [--size 50]   # data/abstracts.json 中尚未翻译的 → trans/in/b_NNN.json
  python scripts/trans_batches.py merge              # trans/out/b_NNN.json → data/abstracts_zh.json（校验后合并）

trans/in 每条 {"id": title_key, "en": 英文摘要}；trans/out 每条 {"id", "zh"}。
英文摘要改变时（按 hash 判断）旧译文作废，重新进入待译。
"""
import glob, hashlib, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABS, ZH = os.path.join(ROOT, "data", "abstracts.json"), os.path.join(ROOT, "data", "abstracts_zh.json")
HASH = os.path.join(ROOT, "data", "abstracts_zh_hash.json")
TIN, TOUT = os.path.join(ROOT, "trans", "in"), os.path.join(ROOT, "trans", "out")
CJK = re.compile(r"[一-鿿]")


def h(t):
    return hashlib.md5(t.encode("utf-8")).hexdigest()[:10]


def load(p, d):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d


def make(size):
    abs_, zh, hs = load(ABS, {}), load(ZH, {}), load(HASH, {})
    todo = [{"id": k, "en": v["en"]} for k, v in abs_.items() if v.get("en") and not (k in zh and hs.get(k) == h(v["en"]))]
    os.makedirs(TIN, exist_ok=True)
    os.makedirs(TOUT, exist_ok=True)
    for f in glob.glob(os.path.join(TIN, "*.json")):
        os.remove(f)
    for n, i in enumerate(range(0, len(todo), size), 1):
        json.dump(todo[i:i + size], open(os.path.join(TIN, f"b_{n:03d}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{len(todo)} abstracts to translate -> {(len(todo) + size - 1) // size} batches in trans/in")


def merge():
    abs_, zh, hs = load(ABS, {}), load(ZH, {}), load(HASH, {})
    ok = bad = 0
    missing = []
    for f in sorted(glob.glob(os.path.join(TIN, "*.json"))):
        ids = [x["id"] for x in json.load(open(f, encoding="utf-8"))]
        of = os.path.join(TOUT, os.path.basename(f))
        try:
            out = {x["id"]: x.get("zh", "") for x in json.load(open(of, encoding="utf-8"))}
        except Exception:  # noqa: BLE001
            out = {}
        for k in ids:
            t = (out.get(k) or "").strip()
            en = abs_.get(k, {}).get("en", "")
            if t and len(CJK.findall(t)) >= max(40, len(en) * 0.12) and en:
                zh[k], hs[k] = t, h(en)
                ok += 1
            else:
                bad += 1
                missing.append(os.path.basename(f))
    json.dump(zh, open(ZH, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(hs, open(HASH, "w", encoding="utf-8"))
    print(f"merged {ok}, missing/invalid {bad}; total translations {len(zh)}")
    if missing:
        print("batches with gaps:", sorted(set(missing)))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "make":
        make(int(a[a.index("--size") + 1]) if "--size" in a else 50)
    elif a and a[0] == "merge":
        merge()
    else:
        print(__doc__)
