Build publication lists for economists from their own homepages/CVs and write one JSON file each.

Method: WebFetch the homepage research/papers page and the CV (prefer the most recent source; a homepage may link a newer CV). WebFetch cannot read PDFs directly: when it saves a PDF locally, run `pdftotext -layout <file> -` on it. For Google Drive files try https://drive.google.com/uc?export=download&id=<ID>; Dropbox: change dl=0 to dl=1. Use WebSearch only if a link is dead (quota small: at most ~4 searches total). Do NOT use OpenAlex/Google Scholar author search (same-name mixing). Include refereed journal articles, forthcoming, R&R, working papers, book chapters; skip op-eds, comments, policy briefs, reports, book reviews, teaching cases, "work in progress" items with no draft. For very long CVs (100+ items) keep all refereed articles and current working papers.

Write `F:\Research_2026\US_EE_Scholar\website\data\papers_raw\<slug>.json` (UTF-8, use a small Python script with json.dump(..., ensure_ascii=False)), exact format:
{"slug": "...", "name": "...", "sources": [urls actually used], "collected": "2026-10-25", "notes": "short English note on source and caveats", "papers": [
 {"title": "...", "authors": ["Full Name", ...], "year": 2024, "venue": "Journal name only (no volume/pages/year)", "status": "已发表|即将发表|修改重投|工作论文", "url": "link from the page/CV if any else \"\"", "abstract": "abstract text if shown verbatim on homepage else null"}]}
Rules:
- status must be exactly one of: 已发表 (published), 即将发表 (forthcoming/accepted), 修改重投 (R&R), 工作论文 (working paper / under review).
- Working papers: venue like "NBER Working Paper" or "Working Paper"; year = latest version year (if none given, the CV/page date year, and say so in notes).
- Authors in the byline order the source gives, including the scholar, names as written. If a source only says "(with X and Y)", use the CV's byline if the CV has one; otherwise list all authors alphabetically by surname (economics convention) and say so in notes.
- year must be an integer; no duplicate titles. Don't invent anything; note ambiguities in notes.
- Only write your own scholars' files; don't touch any other files.

Report back briefly: per scholar, number of papers and sources used, plus problems (one line each).
