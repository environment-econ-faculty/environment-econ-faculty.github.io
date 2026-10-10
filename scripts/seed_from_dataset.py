"""One-time seed: convert US_Top30_Econ_EEE_Faculty.csv into one markdown file per scholar.

Usage: python scripts/seed_from_dataset.py ../US_Top30_Econ_EEE_Faculty.csv
Existing files are NOT overwritten (so hand-added papers are safe); pass --force to overwrite.
"""
import csv, os, re, sys, unicodedata
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "scholars")

RANK = {"Professor": "正教授", "Associate Professor": "副教授", "Assistant Professor": "助理教授"}
APPT = {"primary": "经济系", "joint": "合聘", "secondary/courtesy": "外系挂靠", "own_unit": "本院系"}
UNIT = {"economics": "经济系", "ag_resource_econ": "农经/资源经济", "public_policy": "公共政策", "business": "商学院",
        "environment": "环境学院", "other": "其他"}
TIER = {"primary_field": "核心领域", "secondary_field": "领域之一", "research_only": "相关研究"}
SUB = {"energy": "能源", "environmental": "环境", "climate": "气候", "pollution/health": "污染与健康",
       "natural resources": "自然资源", "agricultural": "农业", "land use": "土地利用", "water": "水资源",
       "transportation": "交通", "other": "其他"}

PAPER_TEMPLATE = """## 论文

<!--
在下方添加论文，每篇以「### 英文标题」开头，字段可留空或删除。示例：

### Paper Title in English
- 中文标题：论文中文标题
- 作者：Author A; Author B
- 年份：2025
- 发表：American Economic Review
- 状态：已发表
- 链接：https://doi.org/...
- 关键词：碳税; 电力市场
- 收录日期：2026-10-10

摘要：在这里粘贴摘要（英文或中文均可，可多段）。

状态可选：已发表 / 即将发表 / 修改重投 / 工作论文
-->
"""


def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def clean(v):
    if v is None:
        return ""
    v = str(v).replace("\r", " ").replace("\n", " ").strip()
    v = re.sub(r"CV data added from CV sub-agent\.\s*", "", v)
    v = re.sub(r"\s*\|\s*$", "", v)
    return "" if v.lower() in ("nan", "none", "null") else v


def yr(v):
    v = clean(v)
    return v[:-2] if v.endswith(".0") else v


def main():
    src = sys.argv[1]
    force = "--force" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    n_new = 0
    with open(src, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            slug = slugify(r["name"])
            path = os.path.join(OUT, slug + ".md")
            if os.path.exists(path) and not force:
                continue
            L = ["---"]
            add = lambda k, v: L.append(f"{k}: {v}") if clean(v) or k in ("中文名",) else None
            add("姓名", clean(r["name"]))
            add("中文名", "")
            add("学校", clean(r["university"]))
            add("职称", RANK.get(r["rank"], r["rank"]))
            add("头衔", clean(r["title_full"]))
            add("单位", clean(r.get("unit")))
            add("单位类型", UNIT.get(clean(r.get("unit_type")), "经济系"))
            add("其他单位", clean(r.get("other_units")))
            add("聘任类型", APPT.get(r["appointment_type"], r["appointment_type"]))
            add("领域层级", TIER.get(r["eee_strength"], r["eee_strength"]))
            subs = [SUB.get(t.strip().lower(), t.strip()) for t in clean(r["eee_subfields"]).split(";") if t.strip()]
            add("研究方向", "; ".join(dict.fromkeys(subs)))
            flags = []
            if r["flag_ag_only"] == "True": flags.append("农业为主")
            if r["flag_inactive_eee"] == "True": flags.append("EEE研究较早")
            add("标记", "; ".join(flags))
            add("自述领域", clean(r["fields_stated"]))
            add("主页", clean(r["homepage_url"]))
            add("CV", clean(r["cv_url"]))
            add("院系页面", clean(r["profile_url"]))
            add("ORCID", clean(r.get("orcid")))
            add("Google Scholar", clean(r.get("google_scholar_url")))
            add("学术兼职", clean(r["other_affiliations"]))
            add("本科", " | ".join([clean(r["ba_institution"]), yr(r["ba_year"]), clean(r["ba_field"])]) if clean(r["ba_institution"]) else "")
            mi = [x.strip() for x in clean(r["ma_institution"]).split(" | ")] if clean(r["ma_institution"]) else []
            my = [x.strip() for x in yr(r["ma_year"]).split(" | ")]
            mf = [x.strip() for x in clean(r["ma_field"]).split(" | ")]
            for i, inst in enumerate(mi):
                add("硕士", " | ".join([inst, my[i] if i < len(my) else "", mf[i] if i < len(mf) else ""]))
            if clean(r["phd_institution"]):
                add("博士", " | ".join([clean(r["phd_institution"]), yr(r["phd_year"]), clean(r["phd_field"])]))
            add("博士导师", clean(r["phd_advisors"]))
            add("首份工作", clean(r["first_job_after_phd"]))
            add("入职现单位", yr(r["year_joined_current"]))
            add("现职称起始", yr(r["year_current_rank"]))
            for p in clean(r["prior_positions"]).split(";"):
                if p.strip():
                    add("经历", p.strip())
            add("研究线索", clean(r["eee_evidence"]))
            add("数据备注", clean(r["notes"]))
            add("CV日期", clean(r["cv_date"]))
            add("信息核对", date.today().isoformat())
            L.append("---")
            L.append("")
            L.append(PAPER_TEMPLATE)
            with open(path, "w", encoding="utf-8", newline="\n") as g:
                g.write("\n".join(L))
            n_new += 1
    print(f"wrote {n_new} scholar files to {OUT}")


if __name__ == "__main__":
    main()
