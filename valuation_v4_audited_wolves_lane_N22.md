# Valuation v4 (data-quality-audited + size-aware) — Wolves Lane, London, N22

**Subject:** 3-bed terraced freehold house, Wolves Lane, London N22 · stated **160 sqm** / 1,718 sqft
**Asking:** "offers over £675,000" · **Current offer:** £660,000
**Prepared:** 2026-06-04 · **Provider:** PropertyData (`api.propertydata.co.uk`); sold = HM Land Registry Price Paid; floor areas = EPC Register. Data pulled **2026-06-04**.
**Method add-ons this run:** `nimrodfisher/data-analytics-skills` — programmatic-eda, data-quality-audit, analysis-assumptions-log, analysis-qa-checklist. All audit scripts were **executed** on the comparable dataset (`comps_3bed_halfmile.csv`); outputs are quoted below.

**Comparable filter (unchanged):** 3-bed · terraced + semi-detached (end-of-terrace folds in) · ≤ 0.5 mi (haversine from Wolves Lane) · ≤ 24 mo (12-mo flagged).

> Honest valuation, not a pitch. Conclusion direction depends on one unverified input (floor area), which is stated, not hidden.

---

## 1. Headline

After a formal data-quality audit removed **one anomalous record** (95 Maryland Road, £235,000 — failed the value-range rule and flagged as a low outlier; no floor area), the clean comparable set is **8 sales**. Three independent estimators were run:

| Estimator | Value for the subject | What it assumes |
|---|---|---|
| Size-blind clean **median** of comps | **£617,500** | ignores that subject is larger than most comps |
| **OLS regression** price~floor area, at 160 sqm | **£681,467** (R²=0.244, ±£93k) | subject genuinely 160 sqm |
| **Similar-size** (≥130 sqm) median | **£682,500** | subject genuinely ~160 sqm |

The two **size-aware** methods converge tightly at **≈ £680,000**; the size-blind median sits at £617,500. **The £660,000 offer falls between them** — about **£21,500 below** the size-adjusted estimate (so *fair, marginally light* if the 160 sqm is real) and about **£42,500 above** the size-blind median (so *full* if the floor area is typical or overstated). **Net: the offer is FAIR and well within every supported range.** The decisive unknown is the **unverified 160 sqm** (§5). Confidence is **moderate-to-low**: the size→price relationship is weak (R²=0.244) and the sample is small.

---

## 2. Data-quality audit (scripts executed, outputs quoted)

Run on `comps_3bed_halfmile.csv` (9 rows pre-clean) via the installed skills:

| Check (script) | Result | Action |
|---|---|---|
| Null/completeness (`null_profiler`) | `floor_sqm` & `price_per_sqm` 11.1% null (1 row) — **WARN** | 95 Maryland Road has no EPC area |
| Outliers, IQR+z (`outlier_detector`) | **2/9 price outliers (22.2%)**: £235,000 (low) & £765,000 (high) | £235k = anomaly; £765k = semi, retained but flagged |
| Value-range vs business rules (`value_range_validator`) | **1 FAIL**: 1 price below £300,000 floor | exclude £235,000 record |
| Duplicates (`duplicate_finder`) | full-row **0**; by-address **0** | none |
| Correlation (`correlation_explorer`) | `sqm↔£/sqm = −0.813`; `sqm↔price = +0.494`; `£/sqm↔price = +0.063` | see §3 |
| Distribution (`distribution_summary`) | price skew **−1.41** (left-skewed) | use **median**, not mean |
| Automated QA gate (`qa_runner`) | **4 checks, 0 FAIL, 0 WARN — PASS** | dataset structurally clean |

**Decision from the audit:** exclude only the £235,000 record (rule violation + outlier + missing size). The £765,000 semi is a statistical high-outlier and a *semi-detached* — retained in the set but treated as the upper bound, not the centre.

---

## 3. Why £/sqm is the wrong lever here — now quantified

The correlation run gives hard numbers behind the earlier hand-observation:

- **floor area ↔ £/sqm = −0.813** (strong negative): bigger homes have materially lower £/sqm. So applying small-home £/sqm to a 160 sqm subject **overstates** — confirmed, not asserted.
- **£/sqm ↔ total price = +0.063** (≈ zero): £/sqm carries almost no information about what a house actually sells for in this set → a poor valuation driver.
- **floor area ↔ total price = +0.494**: size *does* move price, but explains only ~24% of it.

The OLS line is **price ≈ £459,239 + £1,389 × sqm**. The marginal value of floor area (**£1,389/sqm**) is far below the naïve average £/sqm (~£5,000–£6,800), which is exactly why the previous flat-£/sqm extrapolation produced an incredible ~£929k. The size-aware prediction at 160 sqm is **£681,467**, with R²=0.244 and residual sd ±£92,895 → an indicative **1-sd band of ≈ £589,000–£774,000**.

---

## 4. Comparable-sales table (clean set, n=8; £235k anomaly excluded)

Source: PropertyData `/sold-prices` + `/sold-prices-per-sqf`, pulled 2026-06-04. sqm = EPC (indicative).

| Address | Sold | Window | Price | Type | sqm | £/sqm | Dist (mi) | Flag |
|---|---|---|---|---|---|---|---|---|
| 100, Sylvan Avenue, N22 5HY | 2025-05-22 | 12–24mo | £765,000 | semi | 163 | £4,693 | 0.207 | high outlier; semi; ≈subject size |
| 39, Parkhurst Road, N22 8JQ | 2024-08-29 | 12–24mo | £712,500 | terraced | 129 | £5,523 | 0.418 | |
| 67, Wolves Lane, N22 5JD | 2025-05-15 | 12–24mo | £672,000 | terraced | 103 | £6,524 | 0.026 | same street |
| 99, Stirling Road, N22 5BN | 2025-09-08 | 0–12mo | £635,000 | terraced | 96 | £6,615 | 0.432 | |
| 16, Stirling Road, N22 5BU | 2024-08-30 | 12–24mo | £600,000 | terraced | 114 | £5,263 | 0.464 | |
| 22, Stirling Road, N22 5BU | 2025-08-15 | 0–12mo | £600,000 | terraced | 180 | £3,333 | 0.459 | bigger than subject, sold low; EPC area suspect |
| 19, Lyndhurst Road, N22 5AX | 2025-09-19 | 0–12mo | £585,000 | terraced | 86 | £6,802 | 0.273 | |
| 54, White Hart Lane, N22 5RL | 2025-07-25 | 0–12mo | £435,000 | terraced | 87 | £5,000 | 0.496 | borderline distance |

**Excluded by audit:** 95, Maryland Road, N22 5AR — £235,000 (value-range FAIL <£300k; low outlier; no floor area).
**Clean set:** absolute **median £617,500**, mean £625,562, range £435,000–£765,000; £/sqm median £5,393.
**Revealing point:** 22 Stirling Road — **180 sqm (larger than the subject) sold £600,000**, £60,000 below the offer. Bigger did not mean dearer.

---

## 5. Assumptions log (per analysis-assumptions-log skill)

| # | Type | Assumption | Conf | Impact | Validation |
|---|---|---|---|---|---|
| 1 | Data | Subject is **160 sqm** | LOW | HIGH | **Unverified** — pivotal. EPC/measured survey needed. If wrong, valuation shifts toward £617,500. |
| 2 | Data | EPC floor areas on comps are accurate | LOW | MED | Noisy (22 Stirling 180 sqm/£3,333 suspect); regression partly absorbs scatter. |
| 3 | Business | "Comparable" = 3-bed, terraced/semi, ≤0.5 mi, ≤24 mo | HIGH | MED | Per agreed brief (broadened from terraced-only). |
| 4 | Business | £675,000 = floor ("offers over"), not ceiling | HIGH | LOW | Stated in listing. |
| 5 | Statistical | price~sqm linear; median over mean (skew −1.41) | MED | MED | Skew validated by script; linearity weak (R²=0.244). |
| 6 | Data | 2015 £580k is history, not a comp; excluded | HIGH | LOW | Unverifiable (LR 84-mo cap; no house number). Confirm via HM Land Registry. |

Critical assumption: **#1 (160 sqm)** — low confidence, high impact. Everything above £617,500 depends on it.

---

## 6. Assessment of the £660,000 offer

| Benchmark | Figure | £660k vs it |
|---|---|---|
| Size-adjusted OLS @160 sqm | £681,467 | −£21,467 |
| Similar-size (≥130 sqm) median | £682,500 | −£22,500 |
| Size-blind clean median (n=8) | £617,500 | +£42,500 |
| Subject implied £/sqm at offer | £4,125/sqm | below £/sqm comp range (artefact — see §3) |

**Verdict: FAIR.** If the subject is genuinely 160 sqm, two independent size-aware methods put fair value at **≈ £680,000**, so £660,000 is **marginally light (~3% / £21k under)** — and the seller's £675,000 floor is also reasonable. If the 160 sqm is overstated and the home is typical-sized, the size-blind median (£617,500) governs and **£660,000 looks full**. The offer is defensible from either side and sits comfortably inside the regression's 1-sd band (£589k–£774k). The "bigger-sold-for-less" evidence (180 sqm at £600,000) caps any argument for pushing materially above ~£680k for a terraced house; the £765,000 upside is real but is a **semi-detached** and a statistical outlier.

**Reconciliation with prior runs:** loose run ≈£672–690k; strict terraced-only ≈ "£660k full"; similar-size median ≈£656k; this audited size-aware run ≈£680k central with £660k fair. All four place fair value in a **£615k–£685k** band around the offer — none supports pushing well beyond the seller's £675k floor for a terraced house.

---

## 7. Limitations & data gaps

1. **Pivotal unverified input: 160 sqm** (assumption #1). The headline swings from "full" to "marginally light" on this single number. Verify via EPC/measured survey before relying on the size-aware figure.
2. **Weak model.** Size explains only ~24% of price (R²=0.244); the £681,467 point estimate has ±£93k residual sd. Treat as indicative, not precise.
3. **Small sample.** 8 clean comps; only 2 truly similar in size (≥130 sqm); 5 of 8 in the 12–24-month window.
4. **EPC area noise** (assumption #2): 22 Stirling Road's 180 sqm is likely overstated; its absolute £600,000 still stands as evidence.
5. **Type/recency mix:** the £765,000 upper comp is semi-detached (type premium) and a flagged high outlier; the same-street £672,000 (67 Wolves Lane) is 12.7 months old.
6. **2015 subject sale** unverifiable via this API (84-month cap; no house number).
7. **Distance anchor approximate** (mean of Wolves Lane sold coordinates); two comps sit at 0.459–0.496 mi.

*Audit artefacts: `comps_3bed_halfmile.csv`, `terr_semi_halfmile_all.csv`, `vrules.json`, and the source JSON pulls are in this folder for re-verification.*

---
---

# 估值 v4（数据质量审计 + 面积加权）— Wolves Lane, London, N22（简体中文）

**标的物业：** 3 卧排屋永久产权，Wolves Lane, London N22 · 申报面积 **160 平方米** / 1,718 平方英尺
**要价：** "offers over £675,000（高于此价竞标）" · **当前报价：** £660,000
**报告日期：** 2026-06-04 · **数据提供方：** PropertyData（`api.propertydata.co.uk`）；成交 = HM Land Registry Price Paid；楼面面积 = EPC 登记。数据调取于 **2026-06-04**。
**本轮新增方法：** `nimrodfisher/data-analytics-skills` —— programmatic-eda、data-quality-audit、analysis-assumptions-log、analysis-qa-checklist。所有审计脚本均在可比数据集（`comps_3bed_halfmile.csv`）上**实际运行**；输出引用于下。

**可比筛选（不变）：** 3 卧 · 排屋 + 半独立屋（端头排屋并入）· ≤ 0.5 英里（自 Wolves Lane haversine）· ≤ 24 个月（12 个月已标注）。

> 诚实估值，而非推销。结论方向取决于一个未经核实的输入（楼面面积），对此予以明示而非隐藏。

---

## 1. 核心结论

在正式数据质量审计剔除**一条异常记录**（95 Maryland Road，£235,000——未通过取值范围规则，且被标记为低端离群值；无楼面面积）后，干净的可比集合为 **8 笔成交**。运行了三种独立估计量：

| 估计量 | 标的对应值 | 其假设 |
|---|---|---|
| 不计面积的可比**中位数** | **£617,500** | 忽略标的大于多数可比 |
| **OLS 回归** 价格~楼面面积，于 160 平方米 | **£681,467**（R²=0.244，±£93k） | 标的确为 160 平方米 |
| **相似面积**（≥130 平方米）中位数 | **£682,500** | 标的确约 160 平方米 |

两种**面积加权**方法紧密收敛于 **≈ £680,000**；不计面积的中位数为 £617,500。**£660,000 的报价落在二者之间**——比面积调整后估计低约 **£21,500**（若 160 平方米属实，则*公允、略偏低*），比不计面积中位数高约 **£42,500**（若面积属典型或被高估，则*足额*）。**综上：报价属于公允（FAIR），且稳居各支持区间之内。** 决定性的未知量是**未经核实的 160 平方米**（§5）。置信度为**中等偏低**：面积→价格关系较弱（R²=0.244）且样本小。

---

## 2. 数据质量审计（已运行脚本，引用输出）

经安装的技能在 `comps_3bed_halfmile.csv`（清洗前 9 行）上运行：

| 检查（脚本） | 结果 | 处置 |
|---|---|---|
| 空值/完整性（`null_profiler`） | `floor_sqm` 与 `price_per_sqm` 11.1% 为空（1 行）— **WARN** | 95 Maryland Road 无 EPC 面积 |
| 离群值，IQR+z（`outlier_detector`） | **价格 2/9 离群（22.2%）**：£235,000（低）与 £765,000（高） | £235k = 异常；£765k = 半独立，保留但标注 |
| 取值范围 vs 业务规则（`value_range_validator`） | **1 项 FAIL**：1 个价格低于 £300,000 下限 | 剔除 £235,000 记录 |
| 重复（`duplicate_finder`） | 整行 **0**；按地址 **0** | 无 |
| 相关性（`correlation_explorer`） | `面积↔£/㎡ = −0.813`；`面积↔价格 = +0.494`；`£/㎡↔价格 = +0.063` | 见 §3 |
| 分布（`distribution_summary`） | 价格偏度 **−1.41**（左偏） | 采用**中位数**而非平均数 |
| 自动 QA 关卡（`qa_runner`） | **4 项检查，0 FAIL，0 WARN —— 通过** | 数据集结构干净 |

**审计决策：** 仅剔除 £235,000 记录（规则违反 + 离群 + 缺面积）。£765,000 半独立屋为统计高端离群值且为*半独立*——保留于集合中，但视为上限而非中心。

---

## 3. 为何 £/平方米 在此是错误的杠杆——现已量化

相关性运行给出了此前手工观察背后的硬数据：

- **楼面面积 ↔ £/平方米 = −0.813**（强负相关）：更大的房屋 £/平方米 明显更低。故将小户型 £/平方米 套用于 160 平方米标的会**高估**——已证实，而非断言。
- **£/平方米 ↔ 总价 = +0.063**（≈ 零）：在本集合中 £/平方米 几乎不含房屋实际成交价的信息 → 是糟糕的估值驱动因子。
- **楼面面积 ↔ 总价 = +0.494**：面积*确实*影响价格，但仅解释其约 24%。

OLS 直线为 **价格 ≈ £459,239 + £1,389 × 平方米**。楼面面积的边际价值（**£1,389/平方米**）远低于朴素平均 £/平方米（约 £5,000–£6,800），这正是此前平直 £/平方米 外推得出不可信的约 £929k 的原因。面积加权于 160 平方米的预测为 **£681,467**，R²=0.244，残差标准差 ±£92,895 → 指示性 **1 个标准差区间 ≈ £589,000–£774,000**。

---

## 4. 可比成交表（干净集合，n=8；已剔除 £235k 异常）

来源：PropertyData `/sold-prices` + `/sold-prices-per-sqf`，调取于 2026-06-04。平方米 = EPC（仅供参考）。

| 地址 | 成交 | 窗口 | 价格 | 类型 | 平方米 | £/平方米 | 距离(英里) | 标注 |
|---|---|---|---|---|---|---|---|---|
| 100, Sylvan Avenue, N22 5HY | 2025-05-22 | 12–24mo | £765,000 | 半独立 | 163 | £4,693 | 0.207 | 高离群；半独立；≈标的面积 |
| 39, Parkhurst Road, N22 8JQ | 2024-08-29 | 12–24mo | £712,500 | 排屋 | 129 | £5,523 | 0.418 | |
| 67, Wolves Lane, N22 5JD | 2025-05-15 | 12–24mo | £672,000 | 排屋 | 103 | £6,524 | 0.026 | 同街 |
| 99, Stirling Road, N22 5BN | 2025-09-08 | 0–12mo | £635,000 | 排屋 | 96 | £6,615 | 0.432 | |
| 16, Stirling Road, N22 5BU | 2024-08-30 | 12–24mo | £600,000 | 排屋 | 114 | £5,263 | 0.464 | |
| 22, Stirling Road, N22 5BU | 2025-08-15 | 0–12mo | £600,000 | 排屋 | 180 | £3,333 | 0.459 | 大于标的却卖得低；EPC 面积存疑 |
| 19, Lyndhurst Road, N22 5AX | 2025-09-19 | 0–12mo | £585,000 | 排屋 | 86 | £6,802 | 0.273 | |
| 54, White Hart Lane, N22 5RL | 2025-07-25 | 0–12mo | £435,000 | 排屋 | 87 | £5,000 | 0.496 | 距离接近临界 |

**经审计剔除：** 95, Maryland Road, N22 5AR —— £235,000（取值范围 FAIL <£300k；低离群；无楼面面积）。
**干净集合：** 绝对**中位数 £617,500**，平均数 £625,562，全距 £435,000–£765,000；£/平方米 中位数 £5,393。
**揭示性数据点：** 22 Stirling Road —— **180 平方米（大于标的）成交 £600,000**，比报价低 £60,000。更大并未更贵。

---

## 5. 假设日志（依 analysis-assumptions-log 技能）

| # | 类型 | 假设 | 置信 | 影响 | 验证 |
|---|---|---|---|---|---|
| 1 | 数据 | 标的为 **160 平方米** | 低 | 高 | **未核实**——关键。需 EPC/实测。若有误，估值向 £617,500 靠拢。 |
| 2 | 数据 | 可比的 EPC 楼面面积准确 | 低 | 中 | 有噪声（22 Stirling 180㎡/£3,333 存疑）；回归部分吸收散点。 |
| 3 | 业务 | "可比" = 3 卧、排屋/半独立、≤0.5 英里、≤24 个月 | 高 | 中 | 依约定口径（由仅排屋放宽而来）。 |
| 4 | 业务 | £675,000 = 底价（"高于此价竞标"），非上限 | 高 | 低 | 挂牌中载明。 |
| 5 | 统计 | 价格~平方米 为线性；偏度 −1.41 故取中位数 | 中 | 中 | 偏度经脚本验证；线性较弱（R²=0.244）。 |
| 6 | 数据 | 2015 年 £580k 为历史、非可比，已剔除 | 高 | 低 | 无法核实（LR 84 个月上限；无门牌号）。请经 HM Land Registry 核实。 |

关键假设：**#1（160 平方米）**——低置信、高影响。高于 £617,500 的一切都取决于它。

---

## 6. 对 £660,000 报价的评估

| 基准 | 数值 | £660k 相对它 |
|---|---|---|
| 面积调整 OLS @160 平方米 | £681,467 | −£21,467 |
| 相似面积（≥130 平方米）中位数 | £682,500 | −£22,500 |
| 不计面积干净中位数（n=8） | £617,500 | +£42,500 |
| 标的按报价隐含 £/平方米 | £4,125/平方米 | 低于 £/平方米 可比区间（人为产物——见 §3） |

**结论：公允（FAIR）。** 若标的确为 160 平方米，两种独立的面积加权方法将公允价值定于 **≈ £680,000**，故 £660,000 **略偏低（约 3% / 低 £21k）**——卖方 £675,000 的底价亦属合理。若 160 平方米被高估、房屋面积属典型，则由不计面积中位数（£617,500）主导，**£660,000 显得足额**。报价从任一角度均可站得住脚，并稳居回归 1 个标准差区间（£589k–£774k）之内。"更大却卖得更低"的证据（180 平方米成交 £600,000）抑制了将排屋大幅推高至约 £680k 以上的理由；£765,000 的上行确实存在，但其为**半独立屋**且为统计离群值。

**与此前各轮的调和：** 宽松轮 ≈£672–690k；严格仅排屋 ≈"£660k 足额"；相似面积中位数 ≈£656k；本审计面积加权轮 ≈£680k 中心、£660k 公允。四轮均将公允价值置于报价周围的 **£615k–£685k** 区间——均不支持将排屋大幅推高至卖方 £675k 底价之上。

---

## 7. 局限与数据缺口

1. **关键未核实输入：160 平方米**（假设 #1）。结论在"足额"与"略偏低"之间，仅取决于这一个数字。在依赖面积加权数字前，请经 EPC/实测核实。
2. **模型较弱。** 面积仅解释约 24% 的价格（R²=0.244）；£681,467 点估计的残差标准差为 ±£93k。视为指示性，而非精确。
3. **样本小。** 干净可比 8 笔；真正面积相似（≥130 平方米）仅 2 笔；8 笔中有 5 笔位于 12–24 个月窗口。
4. **EPC 面积噪声**（假设 #2）：22 Stirling Road 的 180 平方米很可能被高估；其绝对价 £600,000 仍成立为证据。
5. **类型/近期性混合：** £765,000 上限可比为半独立屋（类型溢价）且为标注的高离群值；同街 £672,000（67 Wolves Lane）成交于 12.7 个月前。
6. **2015 年标的成交** 经本接口无法核实（84 个月上限；无门牌号）。
7. **距离锚点为近似值**（Wolves Lane 成交坐标均值）；两笔可比位于 0.459–0.496 英里。

*审计产物：`comps_3bed_halfmile.csv`、`terr_semi_halfmile_all.csv`、`vrules.json` 及源 JSON 拉取文件均在本文件夹内，供复核。*
