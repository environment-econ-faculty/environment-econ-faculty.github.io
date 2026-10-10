# 能源与环境经济学者库

网址：https://environment-econ-faculty.github.io/

收录美国 US News 2025 经济学排名前 30 的经济系（含并列共 31 所）中研究能源、环境与资源经济学的助理教授、副教授和正教授。每位学者有研究方向、教育背景（本科、硕士、博士）、职业经历，并逐步补充论文与摘要。

## 目录结构

```
data/scholars/<姓名>.md   每位学者一个文件：开头是学者信息，正文是论文（### 开头）
data/scholars/_TEMPLATE.md 新增学者用的模板
data/schools.json         院校列表（排名、中文名、筛查人数）
scripts/build.py          把 data/ 解析成 site/data.js
scripts/seed_from_dataset.py  首次从数据集 CSV 生成学者文件（已执行，一般不需要再运行）
site/                     网页（HTML/CSS/JS）
.github/workflows/deploy.yml  推送后自动构建，并部署到 GitHub Pages
```

## 添加论文（最常见的操作）

1. 在网站的学者页面点击「在 GitHub 上添加论文」，或者直接打开 `data/scholars/<姓名>.md`。
2. 在文件末尾按下面的格式添加论文，每篇以 `###` 开头：

```
### Paper Title
- 中文标题：……
- 作者：A; B
- 年份：2025
- 发表：Journal Name
- 状态：已发表 / 即将发表 / 修改重投 / 工作论文
- 链接：https://...
- 关键词：碳税; 电力
- 收录日期：2026-10-10

摘要：……
```

3. 点 Commit 提交。GitHub Actions 会自动重新构建，大约 1–2 分钟后网站更新。

## 本地检查

```
python scripts/build.py --check
python -m http.server 8000 -d site
```
