"""期刊/出处字段清洗：只保留期刊名（或书名、工作论文系列名），去掉卷期、页码、年份、月份、编者、出版社等。

  "Science, Vol. 357, Issue 6346"                        -> "Science"
  "Journal of Financial Economics 142(2): 499-516"         -> "Journal of Financial Economics"
  "Revise & Resubmit, Journal of Political Economy"        -> "Journal of Political Economy"（状态另有字段）
  "NBER Working Paper No. 32830"                           -> "NBER Working Paper"
  "Handbook of ... (eds. A and B), Elsevier (book chapter)" -> "Handbook of ..."

build.py 在输出时调用 clean_venue()；原始数据 data/papers/*.json 不改。
测试：python scripts/venues.py [N]  打印 N 个样例的清洗前后。
"""
import re

MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|Spring|Summer|Fall|Autumn|Winter)\.?"
STATUS_PREFIX = re.compile(r"^\s*(?:(?:conditionally\s+)?accepted|forthcoming|revise(?:d)?\s*(?:&|and)\s*resubmit(?:ted)?|r\s*&\s*r|"
                           r"resubmitted|submitted|under review|reject\s*(?:&|and)\s*resubmit|minor revision|major revision|"
                           r"to appear|in press)\s*(?:\(\d+(?:st|nd|rd|th)? round\))?\s*(?:at|in|to|,|:|-|–)?\s*", re.I)
STATUS_SUFFIX = re.compile(r"[\s,;(\-–]*\b(?:forthcoming|accepted|in press|to appear|conditionally accepted|"
                           r"revise\s*(?:&|and)\s*resubmit|r\s*&\s*r|under review|submitted|resubmitted)\b.*$", re.I)
# 期刊名之后开始的「引用尾巴」：卷/期/页/年/月等
TAIL = re.compile(r"(?:[,;:.]?\s*(?:\(|\[)?\s*(?:\bvol(?:ume)?\b\.?|\bv\.?\s?\d|\bno\.?\s?\d|\bissue\s*\d|\bpp?\.\s?\d|\bpages?\s+\d|"
                  r"\bart(?:icle)?\.?\s?(?:no\.?)?\s?\d|\be\d{4,}|\b(?:band|heft|bd\.)\s*\d|\d(?!\d*(?:st|nd|rd|th)\b))|"
                  r"[,;]\s*" + MONTHS + r"\b|\s+" + MONTHS + r"\s+\d{4})", re.I)
CHAPTER = re.compile(r"\beds?\.|\(eds?\b|edited by|\bin:?\s|book chapter|\bchapter\b|handbook|encyclopedia|dictionary|companion|"
                     r"proceedings of the|press\b|publishers?\b|elsevier|springer|routledge|wiley|palgrave|north[- ]holland|kluwer", re.I)
PUBLISHER = re.compile(r"^(?:[A-Z][\w.&'\- ]*\s)?(?:University Press|Press|Publishers?|Publishing|Elsevier|Springer(?:-Verlag)?|Routledge|"
                       r"Wiley(?:-Blackwell)?|Palgrave(?: Macmillan)?|North[- ]Holland|Kluwer(?:-Nijhoff)?|Macmillan|World Scientific|"
                       r"Edward Elgar|MIT Press|Brookings Institution(?: Press)?|Emerald|Academic Press|Pergamon)"
                       r"(?:\s+(?:Publishing|Publishers|Press|Ltd|Inc|Co|Group))*\.?$", re.I)  # 整段就是出版社名


def _cut_tail(s):
    m = TAIL.search(s)
    if m and m.start() > 2:
        s = s[:m.start()]
    return s.strip(" ,;:.-–(")


def _names(seg):
    """是否像编者名单：≥2 人（用 and / & / 逗号分隔），每人 ≥2 个大写开头的词，如 "Susan M. Collins and Carol Graham" """
    seg = re.sub(r"^\s*(?:in:?\s+)", "", seg.strip(" ,.;:"), flags=re.I)
    items = [x.strip() for x in re.split(r",\s*(?:and\s+)?|\s+and\s+|\s*&\s*", seg) if x.strip()]
    return len(items) >= 2 and all(re.fullmatch(r"(?:[A-Z][\w'’\-]*\.?\s*){2,5}", x) for x in items)


def _chapter(s):
    """书章/文集：只留书名（去编者、出版社、地点、页码、年份）"""
    s = re.sub(r"\((?:eds?\.?|edited by)\s+[^)]+\)", "", s, flags=re.I)  # "(eds. Barrage and Hsiang)"
    s = re.sub(r"(?<=\w{4})[.,]?\s*(?:edited by|ed\. by)\s.*$", "", s, flags=re.I)  # "Title edited by A, B"
    # "A and B (eds.) Title" / "In A and B, eds., Title" / "Title, A and B (eds). Publisher"
    m = re.search(r"\(?\b(?:eds?\.(?=[\s,)])|eds\b)\)?\s*[,:.]?\s*(?:in:?\s+)?", s, flags=re.I)
    if m:
        before, after = s[:m.start()].strip(" ,"), s[m.end():]
        if (_names(before) or not before) and len(after) > 8:
            got = _chapter_rest(after)
            if len(got) > 4 and not re.fullmatch(r"[\d\s\-–,.]+", got):
                return got
        s = before
    return _chapter_rest(s)


def _chapter_rest(s):
    s = re.sub(r"\([^)]*\)", "", s)  # 其余括号：(book chapter)、(Boulder: Westview Press 1991) 等
    s = re.sub(r"^\s*(?:ch(?:apter)?\.?\s*\d+\s+)?in:?\s+", "", s, flags=re.I)  # "Ch. 1 in Title"
    keep = []
    for p in (x.strip() for x in re.split(r"[,;]", s)):
        if not p:
            continue
        if (PUBLISHER.match(p) or re.search(r"\b(?:Press|Publish\w*)\b", p) or re.search(r":\s*$|^[A-Z][a-z]+(?:, [A-Z]\.[A-Z]\.)?:", p)
                or re.fullmatch(r"[\d\s\-–.,:]+|\d{4}.*|pp?\..*|Vol.*|Chapter.*|Ch\..*", p, flags=re.I)):
            break
        if _names(p):
            continue
        keep.append(p)
    return _cut_tail(", ".join(keep) if keep else s)


def clean_venue(v):
    s = re.sub(r"\s+", " ", v or "").strip()
    if not s:
        return ""
    # 整段引用（"Authors. Title. Journal. 2025 Nov;25(1):4008. doi: ..."）
    if re.search(r"\bdoi:|\bPMID\b", s):
        m = re.search(r"\.\s+([A-Z][^.]{2,80})\.\s+(?:\d{4})", s)
        if m:
            return m.group(1).strip()
    s = re.sub(r"https?://\S+|\bdoi\.org/\S+", "", s).strip()
    # 整段引用："Authors, “Title”, Journal …" / "Authors (2019). “Title.” Journal …" / "Authors (2021). Title. Journal, 101(2)"
    m = re.search(r"[“\"][^”\"]{10,}[”\"]\s*[,.]?\s*(?:in:?\s+)?(.+)$", s)
    if m and re.search(r"\b[A-Z][a-z]+,\s(?:[A-Z]\.|[A-Z][a-z]+)", s[:m.start()]):
        return clean_venue(m.group(1))
    m = re.match(r"^(?:[^()]{0,400}?)\((?:19|20)\d{2}[^)]*\)\.\s+[^.?!]{10,}[.?!]\s+([A-Z][^.]{2,120})", s)
    if m and s.count(",") >= 2:
        return clean_venue(m.group(1))
    if len(re.findall(r"\b[A-Z][a-zà-ÿ'’\-]+,\s(?:[A-Z]\.\s?){1,3}", s)) >= 3 or len(re.findall(r"\b[A-Z][a-z]+ [A-Z]{1,2}\b,", s)) >= 3:
        return ""  # 只有作者名单的残缺引用，宁可留空
    s = re.sub(r"^\(?(?:19|20)\d{2}\)?[\s,.:]+", "", s)  # 开头的年份 "(2015), In: ..." / "2017 Social Science & Medicine"
    s = re.sub(r"^\(with [^)]*\)?\s*[,.]?\s*", "", s, flags=re.I)  # "(with 合作者…)"
    s = STATUS_PREFIX.sub("", s)
    s = STATUS_SUFFIX.sub("", s).strip(" ,;:.-–(")
    if ";" in s:  # "Book (eds. …); NBER Working Paper No. 29479"：只取第一个出处
        s = s.split(";")[0].strip()
    return _balance(_clean(s))


def _clean(s):
    if re.search(r"working paper|discussion paper|wp\b|policy research", s, re.I) and not CHAPTER.search(s):
        s = re.sub(r"(?:\s*[,#]?\s*(?:No\.?|Number|#|w)\s*\d[\w.\-]*|\s+\d[\w.\-]*).*$", "", s, flags=re.I)  # 去编号及其后
        s = re.sub(r",?\s*" + MONTHS + r"\s*\d{0,4}$", "", s, flags=re.I)
        return _cut_tail(s) or s
    if CHAPTER.search(s) and not re.match(r"^(?:Proceedings of the National Academy|PNAS)", s, re.I):
        out = _chapter(s)
        return out or _cut_tail(s)
    return _cut_tail(s) or s


def _balance(s):
    """去掉未闭合的括号尾巴：'Philadelphia, PA (Technical Document Number' -> 'Philadelphia, PA'"""
    if s.count("(") > s.count(")"):
        s = s[:s.rfind("(")].strip(" ,;:.-–")
    s = re.sub(r",\s*Ch\.?$", "", s)
    return s if re.search(r"[A-Za-z]{2}", s) else ""  # 只剩年份/卷期数字的留空


if __name__ == "__main__":
    import glob, json, os, random, sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vs = sorted({p.get("venue") or "" for f in glob.glob(os.path.join(root, "data", "papers", "*.json"))
                 for p in json.load(open(f, encoding="utf-8"))["papers"]} - {""})
    random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 7)
    for v in random.sample(vs, int(sys.argv[1]) if len(sys.argv) > 1 else 80):
        c = clean_venue(v)
        print(("   " if c == v else ">> ") + v[:110] + ("\n      -> " + c if c != v else ""))
