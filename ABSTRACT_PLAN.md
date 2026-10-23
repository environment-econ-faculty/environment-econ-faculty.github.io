# 中英文摘要补全计划（2026-10-22 制定，2026-10-23 已对 EEE 论文执行完毕）

**执行结果**：3,103 篇 EEE 论文中 2,067 篇有核对过的英文摘要（Crossref 988 / OpenAlex 861 / 主页 218）+ 中文翻译；1,036 篇查不到。
重跑：`python scripts/fetch_abstracts.py --no-batch` → `python scripts/trans_batches.py make` → 翻译 trans/in（提示词 trans/PROMPT.md，Haiku agent）→ `trans_batches.py merge` → build。
注意：OpenAlex 免费 key 每日 $1，search 每次 $0.001（约 1000 次/天），singleton 免费——所以按标题找 DOI 用 Crossref。


目标：为 EEE 站全部论文（约 9,586 条，去重后约 8,800 篇）提供**可靠的英文摘要 + 中文翻译**，两者在论文详情页和列表的"摘要"折叠框中一起显示。

## 现状与问题
- 现有摘要 1,058 篇：一部分是 agent 从主页逐字抄录，一部分是 OpenAlex 按标题匹配补的（标注 abs_src=OpenAlex）。
- 已知问题：标题匹配可能配错论文；OpenAlex 的 abstract_inverted_index 有时是 JSTOR 首页文字或残缺文本。所以全部重新查询并校验。
- 无 key 的 OpenAlex 按 IP 每日预算很快耗尽；Semantic Scholar 无 key 直接 429。**建议用户申请免费 key**：OpenAlex（openalex.org 注册）和/或 Semantic Scholar（semanticscholar.org/product/api）。

## 步骤
1. **先补 DOI**：`scripts/resolve_dois.py`（Crossref，免费无 key；已在跑/可续跑，结果在 data/doi_fill.json）。
2. **按 DOI 重新取摘要**（新脚本 scripts/fetch_abstracts.py，纯脚本，不用模型）：
   - 来源优先级：Crossref（DOI，JATS 摘要，去标签）→ OpenAlex（DOI 精确查，`/works/doi:...`，需 key）→ Semantic Scholar batch（`POST /graph/v1/paper/batch`，每次 500 个 DOI，需 key）。
   - 无 DOI 的：标题精确匹配 + 作者姓氏校验（同 resolve_dois 规则）。
   - 校验与清洗：标题一致；长度 300–4000 字；剔除以 "Abstract"/"JSTOR"/"This article" 版权页开头、含 "Purchase"/"Log in" 等页面文本；去 HTML/JATS 标签。
   - 优先级：DOI 来源 > 作者主页原文（abs_src=主页）> 标题匹配。旧的 OpenAlex 标题匹配摘要一律以新结果覆盖，查不到的旧摘要若不通过清洗规则则删除。
   - 输出 data/abstracts.json：{title_key: {"en": ..., "src": "Crossref|OpenAlex|S2|主页", "doi": ...}}
3. **中文翻译（Haiku）**：
   - 脚本把待译摘要切成批次 trans/in/b_NN.json（每批 ~60 篇，id + en）。
   - Haiku agent 读批次、逐篇译成学术中文（术语保留英文缩写，如 PM2.5、DiD），写 trans/out/b_NN.json（id + zh）。≤20 个并发；每批写完即保存。
   - 估算：约 8,000 篇 × 200 词 → 输入 ~2.5M、输出 ~3.5M token（Haiku），约占 5 小时额度 15–25%；按 5 小时窗口分 2 批跑。
4. **构建与前端**：build.py 合并 data/abstracts.json + 翻译到每篇论文（abstract / abstract_zh / abs_src）；
   app.js 的摘要框显示"中文摘要"在上、"英文原文"在下，标注来源；详情页同样。
5. 推送上线；在 About 页注明"中文摘要由模型翻译，以英文原文为准"。
