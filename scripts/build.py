"""Build site/data.js from data/scholars/*.md and data/schools.json.

Each scholar file = front matter (`键: 值` per line, between --- lines) + a markdown body
whose `### 标题` sections are papers. See data/scholars/_TEMPLATE.md.

Usage:
  python scripts/build.py           # build site/data.js
  python scripts/build.py --check   # build and print validation warnings (exit 1 on errors)
"""
import json, os, re, sys, glob
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SITE = os.path.join(ROOT, "site")

LIST_KEYS = {"硕士", "经历"}
ENUMS = {
    "职称": {"正教授", "副教授", "助理教授"},
    "聘任类型": {"经济系", "合聘", "外系挂靠", "本院系"},
    "单位类型": {"经济系", "农经/资源经济", "公共政策", "商学院", "环境学院", "其他"},
    "领域层级": {"核心领域", "领域之一", "相关研究"},
}
SUBFIELDS = ["能源", "环境", "气候", "污染与健康", "自然资源", "农业", "土地利用", "水资源", "交通", "其他"]
STATUS = ["已发表", "即将发表", "修改重投", "工作论文"]
PAPER_KEYS = {"中文标题": "title_zh", "作者": "authors", "年份": "year", "发表": "venue", "状态": "status",
              "链接": "url", "关键词": "keywords", "收录日期": "added", "PDF": "pdf", "代码数据": "replication"}

errors, warnings = [], []


def split_list(v):
    return [x.strip() for x in re.split(r"[;；]", v or "") if x.strip()]


def parse_degree(v):
    parts = [p.strip() for p in v.split("|")]
    parts += [""] * (3 - len(parts))
    year = parts[1]
    return {"school": parts[0], "year": int(year) if year.isdigit() else (year or None), "field": parts[2]}


def parse_front(text, fname):
    m = re.match(r"^﻿?---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        errors.append(f"{fname}: 缺少 --- 包围的信息头")
        return {}, text
    meta = {}
    for ln, line in enumerate(m.group(1).splitlines(), 2):
        if not line.strip() or line.strip().startswith("#"):
            continue
        mm = re.match(r"^\s*([^:：]+?)\s*[:：]\s?(.*)$", line)
        if not mm:
            warnings.append(f"{fname}:{ln}: 无法解析的行：{line[:40]}")
            continue
        k, v = mm.group(1).strip(), mm.group(2).strip()
        if k in LIST_KEYS:
            meta.setdefault(k, [])
            if v:
                meta[k].append(v)
        else:
            meta[k] = v
    return meta, m.group(2)


def parse_papers(body, fname):
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    chunks = re.split(r"^###\s+", body, flags=re.M)[1:]
    papers = []
    for ch in chunks:
        lines = ch.strip().splitlines()
        title = lines[0].strip()
        p = {"title": title}
        rest = []
        for line in lines[1:]:
            mm = re.match(r"^\s*[-*]\s*([^:：]+?)\s*[:：]\s*(.*)$", line)
            if mm and mm.group(1).strip() in PAPER_KEYS and not rest:
                p[PAPER_KEYS[mm.group(1).strip()]] = mm.group(2).strip()
            elif re.match(r"^##\s", line):
                break
            else:
                rest.append(line)
        abstract = "\n".join(rest).strip()
        abstract = re.sub(r"^(摘要|Abstract)\s*[:：]\s*", "", abstract, flags=re.I)
        p["abstract"] = abstract
        y = p.get("year", "")
        p["year"] = int(y) if str(y).isdigit() else None
        if y and p["year"] is None:
            warnings.append(f"{fname}: 论文《{title[:30]}》年份不是数字：{y}")
        if p.get("status") and p["status"] not in STATUS:
            warnings.append(f"{fname}: 论文《{title[:30]}》状态「{p['status']}」不在 {STATUS} 中")
        p["authors"] = split_list(p.get("authors", ""))
        p["eee"] = True
        p["keywords"] = split_list(p.get("keywords", ""))
        papers.append(p)
    return papers


def main():
    check = "--check" in sys.argv
    schools = json.load(open(os.path.join(DATA, "schools.json"), encoding="utf-8"))
    school_names = {s["name"] for s in schools}
    scholars, papers, paper_files = [], [], {}
    for path in sorted(glob.glob(os.path.join(DATA, "scholars", "*.md"))):
        fname = os.path.basename(path)
        if fname.startswith("_"):
            continue
        slug = fname[:-3]
        meta, body = parse_front(open(path, encoding="utf-8").read(), fname)
        if not meta:
            continue
        for k in ("姓名", "学校", "职称"):
            if not meta.get(k):
                errors.append(f"{fname}: 缺少必填字段「{k}」")
        if meta.get("学校") and meta["学校"] not in school_names:
            errors.append(f"{fname}: 学校「{meta['学校']}」不在 data/schools.json 中")
        for k, allowed in ENUMS.items():
            if meta.get(k) and meta[k] not in allowed:
                warnings.append(f"{fname}: {k}「{meta[k]}」应为 {sorted(allowed)} 之一")
        subs = split_list(meta.get("研究方向"))
        for s in subs:
            if s not in SUBFIELDS:
                warnings.append(f"{fname}: 研究方向「{s}」不在 {SUBFIELDS} 中")
        ps = parse_papers(body, fname)
        for p in ps:
            p["src"] = "手动添加"
        auto_path = os.path.join(DATA, "papers", slug + ".json")
        auto_meta = {}
        if os.path.exists(auto_path):
            auto = json.load(open(auto_path, encoding="utf-8"))
            auto_meta = {"sources": auto.get("sources", []), "collected": auto.get("collected", "")}
            have = {re.sub(r"[^a-z0-9]", "", p["title"].lower()) for p in ps}
            for p in auto.get("papers", []):
                if re.sub(r"[^a-z0-9]", "", p["title"].lower()) not in have:
                    ps.append(p)
        ps.sort(key=lambda p: (-(p.get("year") or 0), STATUS.index(p["status"]) if p.get("status") in STATUS else 9))
        sc = {
            "id": slug, "name": meta.get("姓名", ""), "name_zh": meta.get("中文名", ""),
            "school": meta.get("学校", ""), "rank": meta.get("职称", ""), "title": meta.get("头衔", ""),
            "appt": meta.get("聘任类型", ""), "unit": meta.get("单位", ""), "unit_type": meta.get("单位类型", "经济系"),
            "other_units": meta.get("其他单位", ""), "orcid": meta.get("ORCID", ""), "scholar_url": meta.get("Google Scholar", ""), "tier": meta.get("领域层级", ""), "subfields": subs,
            "flags": split_list(meta.get("标记")), "fields_stated": meta.get("自述领域", ""),
            "homepage": meta.get("主页", ""), "cv": meta.get("CV", ""), "profile": meta.get("院系页面", ""),
            "affiliations": meta.get("学术兼职", ""),
            "ba": parse_degree(meta["本科"]) if meta.get("本科") else None,
            "ma": [parse_degree(x) for x in meta.get("硕士", [])],
            "phd": parse_degree(meta["博士"]) if meta.get("博士") else None,
            "advisors": meta.get("博士导师", ""), "first_job": meta.get("首份工作", ""),
            "joined": meta.get("入职现单位", ""), "rank_since": meta.get("现职称起始", ""),
            "career": meta.get("经历", []), "evidence": meta.get("研究线索", ""),
            "notes": meta.get("数据备注", ""), "cv_date": meta.get("CV日期", ""), "checked": meta.get("信息核对", ""),
            "n_papers": len(ps), "n_eee": sum(1 for p in ps if p.get("eee")),
            "paper_sources": auto_meta.get("sources", []), "papers_collected": auto_meta.get("collected", ""),
        }
        scholars.append(sc)
        full = []
        for i, p in enumerate(ps):
            full.append({k: p.get(k) for k in ("title", "title_zh", "authors", "year", "venue", "status", "url", "doi",
                                                 "abstract", "abs_src", "keywords", "eee", "src", "pdf", "replication") if p.get(k)})
            papers.append([slug, i, p.get("title", ""), p.get("year") or 0, p.get("venue") or "",
                           STATUS.index(p["status"]) if p.get("status") in STATUS else 3, 1 if p.get("eee") else 0,
                           1 if p.get("abstract") else 0, ", ".join((p.get("authors") or [])[:6])])
        paper_files[slug] = full

    used = {s["school"] for s in scholars}
    for s in schools:
        s["n"] = sum(1 for x in scholars if x["school"] == s["name"])
    tz = timezone(timedelta(hours=8))
    out = {
        "generated": datetime.now(tz).strftime("%Y-%m-%d"),
        "schools": schools, "scholars": scholars, "papers": papers,
        "subfields": SUBFIELDS, "statuses": STATUS, "unit_types": ["经济系", "农经/资源经济", "公共政策", "商学院", "环境学院", "其他"],
        "paper_cols": ["scholar", "i", "title", "year", "venue", "status", "eee", "has_abs", "authors"],
    }
    os.makedirs(os.path.join(SITE, "papers"), exist_ok=True)
    for fn in os.listdir(os.path.join(SITE, "papers")):
        os.remove(os.path.join(SITE, "papers", fn))
    for slug, full in paper_files.items():
        with open(os.path.join(SITE, "papers", slug + ".json"), "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(SITE, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.EEE_DATA = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"{len(scholars)} scholars, {len(papers)} papers, {len(used)} schools -> site/data.js")
    if check or errors:
        for w in warnings:
            print("WARN ", w)
        for e in errors:
            print("ERROR", e)
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
