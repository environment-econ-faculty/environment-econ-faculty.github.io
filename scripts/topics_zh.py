"""论文话题分类（中文标签，每篇最多 2 个），按标题 + 摘要关键词识别。

classify(title, abstract, eee) -> [话题序号, ...]
  命中关键词：取优先级最高的两个话题；
  未命中：EEE 相关论文 ->「其他环境议题」，否则 ->「其他经济学」。
"""
import re

TOPICS = [
    ("气候影响：高温与极端天气", r"climat\w* (change|impact|damage|shock|risk|variab)|temperature|heat|heatwave|extreme (weather|heat|event)|global warming|warming"),
    ("气候适应与韧性", r"adapt\w*|resilien\w*"),
    ("碳定价与气候政策", r"carbon (tax|pric|market|border|leakage|credit|offset|dioxide)|emission\w* (trading|tax|permit|reduc)|cap.and.trade|ets|climate polic\w*|net.zero|decarboni\w*|paris agreement|mitigation|greenhouse|co2|social cost of carbon|climate change polic\w*"),
    ("空气污染与健康", r"air pollution|air quality|pm2\.5|particulate|ozone|smog|wildfire smoke|pollution.{0,30}(health|mortality|birth|infant|cognit|asthma)"),
    ("污染与环境规制", r"pollut\w*|clean air act|clean water act|epa|environmental (regulation|polic\w*|enforcement|standard|compliance|inspection|protection)|toxic"),
    ("可再生能源：光伏与风电", r"solar|wind (power|energy|farm|turbine)|renewable\w*|clean energy|green energy"),
    ("电力市场、电网与储能", r"electricity|power (plant|sector|market|grid|outage)|grid|interconnection|utilit(y|ies)|batter(y|ies)|energy storage|transmission|blackout|wholesale"),
    ("电动车、交通与燃油", r"electric vehicle\w*|evs?|vehicle\w*|automobile\w*|fuel economy|gasoline|transport\w*|congestion|driving|cars?|traffic"),
    ("油气、煤炭与化石能源", r"oil|natural gas|coal|fracking|shale|fossil fuel\w*|methane|petroleum|lng|crude|pipeline"),
    ("能源需求与能效", r"energy (efficien\w*|demand|consumption|use|saving|poverty|burden|price\w*)|appliance\w*|heating|air condition\w*|home energy|building\w*"),
    ("自然灾害、洪水、野火与保险", r"disaster\w*|flood\w*|hurricane\w*|wildfire\w*|storm\w*|insurance|sea.level|earthquake\w*"),
    ("农业与粮食", r"agricultur\w*|crop\w*|farm\w*|food|fertili[sz]er\w*|livestock|yield\w*|rural"),
    ("水资源与干旱", r"water|drought\w*|groundwater|irrigation|aquifer\w*"),
    ("土地利用、毁林与保护", r"land.use|deforest\w*|forest\w*|conservation|biodivers\w*|ecosystem\w*|protected area\w*|payments? for ecosystem|wildlife|species"),
    ("环境正义与分配效应", r"environmental justice|disparit\w*|inequalit\w*|distribution(al)? (effect|impact|consequence)\w*|low.income|racial|equity|regressiv\w*"),
    ("绿色金融、ESG 与气候风险", r"esg|green (bond|financ\w*|invest\w*)|sustainable financ\w*|climate (finance|risk)|carbon (risk|disclosure|footprint)|stranded asset\w*|greenwash\w*"),
    ("绿色创新与清洁技术", r"(green|clean|low.carbon|climate) (innovation|technolog\w*)|directed technical change|innovation.{0,30}(climate|energy|clean|green)"),
    ("自然资源、矿产与渔业", r"mining|mineral\w*|lithium|cobalt|natural resource\w*|fisher(y|ies)|fish\w*|resource curse|exhaustible"),
    ("发展中国家的能源与环境", r"electrification|cookstove\w*|energy access|indoor air|(india|china|africa|bangladesh|kenya|indonesia|brazil).{0,50}(electric|pollut|energy|environment|climate)"),
    ("环境价值评估", r"willingness to pay|valuation|hedonic|contingent|value of (a )?statistical life|benefit.cost|non.?market"),
    ("气候移民与冲突", r"migration.{0,40}(climat|environment|weather|disaster)|(climat|weather|drought|temperature).{0,40}(migration|conflict|violence)"),
    ("废弃物、塑料与回收", r"plastic\w*|waste|recycl\w*|landfill\w*|circular economy"),
]
OTHER_ENV, OTHER = "其他环境议题", "其他经济学"
NAMES = [n for n, _ in TOPICS] + [OTHER_ENV, OTHER]
RULES = [(i, re.compile(r"\b(?:" + rx + r")\b", re.I)) for i, (_, rx) in enumerate(TOPICS)]


def classify(title, abstract="", eee=False):
    t = f"{title or ''} {(abstract or '')[:1500]}"
    out = []
    for i, rx in RULES:
        if rx.search(title or ""):  # title hits rank first
            out.append(i)
    for i, rx in RULES:
        if i not in out and rx.search(t):
            out.append(i)
    if not out:
        return [NAMES.index(OTHER_ENV if eee else OTHER)]
    return out[:2]
