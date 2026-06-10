# Strict-Comparable Valuation — Wolves Lane, London, N22

**Subject:** 3-bed terraced freehold house, Wolves Lane, London N22 · stated 160 sqm / 1,718 sqft
**Asking:** "offers over £675,000" · **Current offer:** £660,000
**Prepared:** 2026-06-04 · **Provider:** PropertyData (`api.propertydata.co.uk`), sold data = HM Land Registry Price Paid; floor areas = EPC Register. All sold figures pulled **2026-06-04**.

**Hard filters applied (any single failure = excluded):** terraced house · **exactly 3 bedrooms** (confirmed; null-bedroom records excluded) · **≤ 0.5 miles** from the subject · **sold ≤ 12 months** (extension to 24 months not triggered — see §1). Distance measured by haversine from the Wolves Lane sold-sale coordinates (51.6082, −0.1028), the best available anchor for the subject's street.

> Valuation, not a pitch. Small honest samples are reported as small. Where a prescribed method produces an unreliable number, that is stated, not hidden.

---

## 1. Headline

Five comparables pass every hard filter (terraced · 3-bed · ≤0.5 mi · ≤12 months); **four are usable** for £/sqm (one has no floor area and an anomalous price). Because ≥3 qualified within 12 months, the window was **not** extended to 24 months. On a small sample like this the **median** is used, not the mean.

The prescribed £/sqm method gives a median of **£5,808/sqm**, which applied to 160 sqm implies **≈ £929,000 (range £533,000–£1,088,000)** — but **this figure is not credible** and is not the valuation: no qualifying comparable sold above £635,000 (12-month) or £672,000 (same-street, just outside the window), so a ~£929k result is an artefact of multiplying small-house £/sqm rates by a large *stated* floor area, compounded by noisy EPC areas (see §3). The **trustworthy evidence is the absolute sold prices**: credible 3-bed terraced within 0.5 mi / 12 months sold for **£435,000–£635,000 (median £592,500)**, with the single closest match — 67 Wolves Lane, same street, 3-bed — at **£672,000** (12.7 months old, flagged separately). A defensible fair-value range is therefore approximately **£585,000–£660,000** for a typical-sized 3-bed terraced here, reaching toward **£672,000** only if the subject's larger-than-comparable 160 sqm is genuine and verified. **The £660,000 offer sits at the very top of what this strict, recent evidence supports — it is full, not light** (see §5). *This is an **indicative** valuation given the small sample.*

---

## 2. Comparable-sales table (SOLD only)

### Qualifying comps — pass ALL hard filters (terraced · 3-bed · ≤0.5 mi · ≤12 mo)
Source: PropertyData `/sold-prices` + `/sold-prices-per-sqf`, pulled 2026-06-04. sqm = EPC-derived (indicative).

| # | Address | Sold date | Price | Beds | Type | sqm | £/sqm | Dist (mi) |
|---|---|---|---|---|---|---|---|---|
| 1 | 99, Stirling Road, N22 5BN | 2025-09-08 | £635,000 | 3 | terraced | 96 | £6,615 | 0.432 |
| 2 | 22, Stirling Road, N22 5BU | 2025-08-15 | £600,000 | 3 | terraced | 180 ⚠ | £3,333 | 0.459 |
| 3 | 19, Lyndhurst Road, N22 5AX | 2025-09-19 | £585,000 | 3 | terraced | 86 | £6,802 | 0.273 |
| 4 | 54, White Hart Lane, N22 5RL | 2025-07-25 | £435,000 | 3 | terraced | 87 | £5,000 | 0.496 ◐ |
| 5 | 95, Maryland Road, N22 5AR | 2025-07-11 | £235,000 ⚠ | 3 | terraced | n/a | n/a | 0.152 |

⚠ #2: 180 sqm with the lowest £/sqm (£3,333) — EPC area almost certainly overstated; size/£sqm unreliable.
⚠ #5: £235,000 is ~⅓ of neighbouring 3-bed sales and has no floor area → treated as a probable non-arm's-length / data anomaly; **excluded from both the £/sqm median and the absolute-price stats** (it passes the filters but is unusable). Shown for full transparency.
◐ #4: 0.496 mi — inside the 0.5-mile cap but borderline; would drop out under a slightly different street anchor.

**Usable for £/sqm: comps #1–#4 (n = 4).** Absolute-price stats (credible #1–#4): median **£592,500**, mean £563,750, range **£435,000–£635,000**.

### Flagged — 12-to-24-month window (NOT in the valuation set; shown because same-street)
| Address | Sold date | Price | Beds | Type | sqm | £/sqm | Dist (mi) | Why not used |
|---|---|---|---|---|---|---|---|---|
| 67, Wolves Lane, N22 5JD | 2025-05-15 | £672,000 | 3 | terraced | 103 | £6,524 | 0.026 | 12.7 months old → outside the 12-month window. Extension not triggered (≥3 comps within 12 mo). |

### Excluded — proof the filters bit (each failed exactly one hard criterion)
| Address | Sold | Price | Failed criterion |
|---|---|---|---|
| 64, Stirling Road, N22 5BP | 2025-07-24 | £635,000 | **Bedrooms** — 4-bed |
| 6, Forfar Road, N22 5QE | 2025-12-09 | £725,000 | **Bedrooms** — 4-bed |
| 4, Stirling Road, N22 5BU | 2025-10-30 | £620,000 | **Bedrooms** — 2-bed |
| 46, Solway Road, N22 5BX | 2025-12-16 | £625,000 | **Bedrooms** — 2-bed |
| 65, Perth Road, N22 5QD | 2026-02-20 | £650,000 | **Bedrooms** — unconfirmed (null); also 0.500 mi |
| 37, Berwick Road, N22 5QB | 2025-07-25 | £840,000 | **Bedrooms** — unconfirmed (null) |
| 25, Sandford Avenue, N22 5EJ | 2025-07-07 | £575,000 | **Distance** — 0.531 mi |
| 2, Williams Grove, N22 5NR | 2025-07-11 | £615,000 | **Distance** — 0.568 mi |
| 33, Thorold Road, N22 8YE | 2025-07-25 | £880,000 | **Distance** — 0.682 mi |

(Additionally, **7 terraced houses within 0.5 mi / 12 months were excluded because their bedroom count was not recorded** and 3-bed could not be confirmed — see §6.)

---

## 3. £/sqm analysis — subject vs comparable median & range

- **Comparable £/sqm (usable comps #1–#4):** **median £5,808/sqm**, range **£3,333–£6,802/sqm** (PropertyData, pulled 2026-06-04). Median used, not mean — small, skewed sample.
- **Subject at the £660,000 offer:** £660,000 ÷ 160 sqm = **£4,125/sqm**.
- **Methodology output (comparable median £/sqm × 160 sqm):** median **£929,200**; range **£533,280–£1,088,320**.

**Why this output is not used as the valuation:** the four comps span 86–96 sqm (plus one suspect 180 sqm). Smaller houses structurally carry a **higher** £/sqm than larger ones, so applying their per-sqm rate to a 160 sqm property over-extrapolates. The EPC areas are also noisy — comp #2 (180 sqm, £3,333/sqm) versus comp #3 (86 sqm, £6,802/sqm) is a 2× spread within one strict set. Crucially, **no qualifying transaction reached even £700,000**, so a £929k central figure has zero support in actual sales. The £/sqm result is reported because the brief requires it, but the **absolute sold prices (§2) are weighted as the reliable evidence.**

---

## 4. Subject sale-history verification (history — NOT a comparable)

**Stated prior sale: £580,000 in 2015. Status: NOT VERIFIABLE via this data; correctly EXCLUDED from all comparables and averages.**

- PropertyData's HM Land Registry Price Paid feed is capped at an **84-month** look-back (~mid-2019 from today), so a **2015** transaction cannot be returned by the API.
- No house number / full postcode was supplied, so the subject's specific title/UPRN cannot be isolated to confirm the record independently.
- Per the brief, this 2015 figure is treated **only** as sale history and was never used as a comp or averaged in.

**Recommendation:** confirm the £580,000 / 2015 figure via the free HM Land Registry Price Paid search using the full address.

---

## 5. Assessment of the £660,000 offer

Framing: £675,000 is "offers over" — a floor inviting higher bids, not a ceiling — so the test is "where does £660,000 sit against the strict sold evidence?", not a percentage of asking.

| Benchmark (strict evidence) | Figure | £660k vs it |
|---|---|---|
| Credible 3-bed terraced ≤0.5 mi / 12 mo — **median** | £592,500 | **+£67,500 above** |
| Credible 3-bed terraced ≤0.5 mi / 12 mo — **max** | £635,000 | **+£25,000 above** |
| Same-street 3-bed (67 Wolves Lane, 12.7 mo) | £672,000 | −£12,000 below |
| £/sqm method (median; not credible) | £929,200 | far below |

**Verdict: the £660,000 offer is FULL — at or slightly above what the strict, recent, like-for-like evidence supports.** On 12-month comparables alone, every credible qualifying sale was **£635,000 or lower**, so the strict recent evidence **does not independently reach £660,000**. The offer is justified up to "fair" only by (a) the same-street 3-bed at £672,000, which sits *outside* the 12-month window, and/or (b) the subject's 160 sqm being genuinely larger than the 86–96 sqm comps and thus commanding a size premium — a premium no same-size comparable in the strict set confirms. 

Plainly stated, as the brief requires: **on strict 12-month comparables, fair value indicates roughly £585,000–£635,000 — below the £660,000 offer.** £660,000 is therefore not light; it is full-to-strong, with any justification above ~£635k resting on the (older) same-street sale and an unverified size advantage. A buyer is paying at the top of the defensible band, not below it.

---

## 6. Limitations & data gaps

1. **Small sample.** Only 5 comps pass all filters; **4 usable** for £/sqm (one no-size anomaly). This is an **indicative**, not conclusive, valuation. No criterion was loosened to enlarge it.
2. **£/sqm output unreliable** (§3): small-house rates extrapolated onto a large stated area + noisy EPC floor areas → the £929k median has no transactional support and is not used.
3. **Subject's 160 sqm is unverified** and is larger than every credible comp (86–96 sqm). The valuation is highly sensitive to this: if accurate, value leans to the upper band; if overstated, to the lower. An EPC / measured survey is advised.
4. **7 terraced houses within 0.5 mi / 12 months were excluded for unconfirmed bedroom count** (null in the Land Registry/EPC match). Some may genuinely be 3-bed and would, if confirmed, enlarge the sample (their prices ranged £478,000–£840,000). Bedroom-count coverage is the single biggest data gap here.
5. **Distance anchor approximate.** The subject's exact position on Wolves Lane is unknown; the anchor is the mean of the street's sold-sale coordinates. Comp #4 (0.496 mi) and excluded 65 Perth Road (0.500 mi) are borderline and could flip under a different anchor point.
6. **Best comp is just outside recency.** 67 Wolves Lane (same street, 3-bed, £672,000) is 12.7 months old, so it is flagged and excluded from the valuation set rather than driving it — even though it is the most physically comparable property available.
7. **2015 subject sale unverifiable** via this API (84-month cap; no house number) — §4.

---
---

# 严格可比估值 — Wolves Lane, London, N22（简体中文）

**标的物业：** 3 卧排屋（terraced）永久产权（freehold），Wolves Lane, London N22 · 申报面积 160 平方米 / 1,718 平方英尺
**要价：** "offers over £675,000（高于此价竞标）" · **当前报价：** £660,000
**报告日期：** 2026-06-04 · **数据提供方：** PropertyData（`api.propertydata.co.uk`），成交数据 = HM Land Registry Price Paid；楼面面积 = EPC 登记。所有成交数字调取于 **2026-06-04**。

**已施加的硬性筛选条件（任一不符即排除）：** 排屋 · **恰为 3 卧**（须确认；卧室数缺失的记录一律排除）· 距标的 **≤ 0.5 英里** · 成交 **≤ 12 个月**（未触发延展至 24 个月——见 §1）。距离以 Wolves Lane 成交坐标（51.6082, −0.1028）为锚，按 haversine 公式计算，此为该街道最佳可用锚点。

> 估值，而非推销。小样本如实呈现为小样本。当规定方法得出不可靠数字时，予以明示而非隐藏。

---

## 1. 核心结论

有 5 套可比通过全部硬性筛选（排屋 · 3 卧 · ≤0.5 英里 · ≤12 个月）；其中 **4 套可用于** £/平方米 计算（1 套无楼面面积且价格异常）。由于 12 个月内已有 ≥3 套合格，**未**延展至 24 个月。对如此小样本，采用**中位数**而非平均数。

规定的 £/平方米 方法得出中位数 **£5,808/平方米**，套用于 160 平方米隐含 **≈ £929,000（区间 £533,000–£1,088,000）**——但**该数字不可信**，并非最终估值：没有任何合格可比成交高于 £635,000（12 个月内）或 £672,000（同街，刚好超出窗口），因此约 £929k 的结果是"用小户型 £/平方米 单价乘以一个较大的*申报*面积"的人为产物，并叠加了 EPC 面积噪声（见 §3）。**可信的证据是绝对成交价**：0.5 英里 / 12 个月内可信的 3 卧排屋成交价为 **£435,000–£635,000（中位数 £592,500）**，而最接近的单一可比——67 Wolves Lane，同街，3 卧——为 **£672,000**（成交于 12.7 个月前，单独标注）。因此可站得住脚的公允价值区间约为 **£585,000–£660,000**（针对此处典型面积的 3 卧排屋），仅当标的物业大于可比的 160 平方米属实并经核实时，方可上探至 **£672,000**。**£660,000 的报价处于此严格近期证据所支持区间的最顶端——属于足额，而非偏低**（见 §5）。*鉴于样本量小，本估值为**指示性**。*

---

## 2. 可比成交表（仅 SOLD 成交）

### 合格可比 — 通过全部硬性筛选（排屋 · 3 卧 · ≤0.5 英里 · ≤12 个月）
来源：PropertyData `/sold-prices` + `/sold-prices-per-sqf`，调取于 2026-06-04。平方米 = EPC 推导（仅供参考）。

| # | 地址 | 成交日期 | 价格 | 卧室 | 类型 | 平方米 | £/平方米 | 距离(英里) |
|---|---|---|---|---|---|---|---|---|
| 1 | 99, Stirling Road, N22 5BN | 2025-09-08 | £635,000 | 3 | 排屋 | 96 | £6,615 | 0.432 |
| 2 | 22, Stirling Road, N22 5BU | 2025-08-15 | £600,000 | 3 | 排屋 | 180 ⚠ | £3,333 | 0.459 |
| 3 | 19, Lyndhurst Road, N22 5AX | 2025-09-19 | £585,000 | 3 | 排屋 | 86 | £6,802 | 0.273 |
| 4 | 54, White Hart Lane, N22 5RL | 2025-07-25 | £435,000 | 3 | 排屋 | 87 | £5,000 | 0.496 ◐ |
| 5 | 95, Maryland Road, N22 5AR | 2025-07-11 | £235,000 ⚠ | 3 | 排屋 | n/a | n/a | 0.152 |

⚠ #2：180 平方米却对应最低 £/平方米（£3,333）——EPC 面积几乎可以肯定被高估；面积/单价不可靠。
⚠ #5：£235,000 约为邻近 3 卧成交的三分之一且无楼面面积 → 视为很可能的非公平交易/数据异常；**从 £/平方米 中位数及绝对价格统计中均予排除**（虽通过筛选但不可用）。为完全透明仍列出。
◐ #4：0.496 英里——在 0.5 英里上限之内但接近临界；若街道锚点略有不同则会被剔除。

**可用于 £/平方米：可比 #1–#4（n = 4）。** 绝对价格统计（可信 #1–#4）：中位数 **£592,500**，平均数 £563,750，全距 **£435,000–£635,000**。

### 标注 — 12 至 24 个月窗口（不计入估值集；因同街而展示）
| 地址 | 成交日期 | 价格 | 卧室 | 类型 | 平方米 | £/平方米 | 距离(英里) | 未采用原因 |
|---|---|---|---|---|---|---|---|---|
| 67, Wolves Lane, N22 5JD | 2025-05-15 | £672,000 | 3 | 排屋 | 103 | £6,524 | 0.026 | 成交于 12.7 个月前 → 超出 12 个月窗口。延展条件未触发（12 个月内已有 ≥3 套）。 |

### 排除项 — 证明筛选确实生效（各自恰好不符一项硬性条件）
| 地址 | 成交 | 价格 | 不符条件 |
|---|---|---|---|
| 64, Stirling Road, N22 5BP | 2025-07-24 | £635,000 | **卧室** — 4 卧 |
| 6, Forfar Road, N22 5QE | 2025-12-09 | £725,000 | **卧室** — 4 卧 |
| 4, Stirling Road, N22 5BU | 2025-10-30 | £620,000 | **卧室** — 2 卧 |
| 46, Solway Road, N22 5BX | 2025-12-16 | £625,000 | **卧室** — 2 卧 |
| 65, Perth Road, N22 5QD | 2026-02-20 | £650,000 | **卧室** — 未确认（缺失）；且 0.500 英里 |
| 37, Berwick Road, N22 5QB | 2025-07-25 | £840,000 | **卧室** — 未确认（缺失） |
| 25, Sandford Avenue, N22 5EJ | 2025-07-07 | £575,000 | **距离** — 0.531 英里 |
| 2, Williams Grove, N22 5NR | 2025-07-11 | £615,000 | **距离** — 0.568 英里 |
| 33, Thorold Road, N22 8YE | 2025-07-25 | £880,000 | **距离** — 0.682 英里 |

（此外，**0.5 英里 / 12 个月内有 7 套排屋因卧室数未记录、无法确认为 3 卧而被排除**——见 §6。）

---

## 3. £/平方米 分析 — 标的 vs 可比中位数与区间

- **可比 £/平方米（可用可比 #1–#4）：** **中位数 £5,808/平方米**，区间 **£3,333–£6,802/平方米**（PropertyData，调取于 2026-06-04）。采用中位数而非平均数——样本小且偏斜。
- **标的按 £660,000 报价：** £660,000 ÷ 160 平方米 = **£4,125/平方米**。
- **方法输出（可比中位数 £/平方米 × 160 平方米）：** 中位数 **£929,200**；区间 **£533,280–£1,088,320**。

**为何此输出不作为估值采用：** 四套可比面积为 86–96 平方米（外加一套存疑的 180 平方米）。小户型的 £/平方米 单价在结构上**高于**大户型，故将其单价套用于 160 平方米会过度外推。EPC 面积亦有噪声——可比 #2（180 平方米，£3,333/平方米）与可比 #3（86 平方米，£6,802/平方米）在同一严格集合内相差 2 倍。关键在于，**没有任何合格交易达到 £700,000**，因此 £929k 的中心数字在实际成交中毫无支撑。£/平方米 结果因任务要求而列出，但以 §2 的**绝对成交价为可靠证据加权。**

---

## 4. 标的物业成交历史核验（历史 — 非可比）

**申报上次成交：2015 年 £580,000。状态：经本数据无法核实；已正确地从所有可比与平均中排除。**

- PropertyData 的 HM Land Registry Price Paid 数据回溯上限为 **84 个月**（自今日起约至 2019 年中），故 **2015 年**交易无法由接口返回。
- 未提供门牌号 / 完整邮编，无法锁定标的物业的具体产权/UPRN 以独立确认记录。
- 按任务要求，此 2015 数字**仅**作为成交历史，从未用作可比或计入平均。

**建议：** 通过免费的 HM Land Registry Price Paid，按完整地址核实 £580,000 / 2015 的数字。

---

## 5. 对 £660,000 报价的评估

框定：£675,000 为 "offers over（高于此价竞标）"——是邀请更高出价的**底价**，而非上限——故检验标准是"£660,000 相对严格成交证据处于何处"，而非占要价的百分比。

| 基准（严格证据） | 数值 | £660k 相对它 |
|---|---|---|
| 可信 3 卧排屋 ≤0.5 英里 / 12 个月 — **中位数** | £592,500 | **高出 £67,500** |
| 可信 3 卧排屋 ≤0.5 英里 / 12 个月 — **最高** | £635,000 | **高出 £25,000** |
| 同街 3 卧（67 Wolves Lane，12.7 个月） | £672,000 | 低 £12,000 |
| £/平方米 方法（中位数；不可信） | £929,200 | 远低于 |

**结论：£660,000 的报价属于足额（FULL）——处于严格、近期、同类可比证据所支持区间的顶端或略高。** 仅就 12 个月可比而言，每一笔可信合格成交均为 **£635,000 或更低**，故严格近期证据**本身并未达到 £660,000**。该报价仅凭以下因素方可上探至"公允"：(a) 同街 3 卧成交 £672,000，但其位于 12 个月窗口*之外*；及/或 (b) 标的 160 平方米确实大于 86–96 平方米的可比、从而带来面积溢价——而严格集合中没有任何同等面积的可比能证实此溢价。

按任务要求明确陈述：**就严格 12 个月可比而言，公允价值指示约为 £585,000–£635,000——低于 £660,000 的报价。** 因此 £660,000 并不偏低；它属于足额至偏强，任何高于约 £635k 的理由都依赖于（较旧的）同街成交与未经核实的面积优势。买方支付的是可站得住脚区间的顶端，而非低于该区间。

---

## 6. 局限与数据缺口

1. **样本小。** 仅 5 套通过全部筛选；**4 套可用**于 £/平方米（1 套无面积、属异常）。本估值为**指示性**而非结论性。未为扩大样本而放宽任何条件。
2. **£/平方米 输出不可靠**（§3）：小户型单价外推至大面积 + EPC 面积噪声 → £929k 中位数无成交支撑，未予采用。
3. **标的 160 平方米未经核实**，且大于每一套可信可比（86–96 平方米）。估值对此高度敏感：若属实，价值偏向区间上半部；若高估，则偏向下半部。建议进行 EPC / 实测测量。
4. **0.5 英里 / 12 个月内有 7 套排屋因卧室数未确认（土地登记/EPC 匹配中缺失）而被排除。** 其中部分可能确为 3 卧，若经确认将扩大样本（其价格区间为 £478,000–£840,000）。卧室数覆盖率是此处最大的单一数据缺口。
5. **距离锚点为近似值。** 标的在 Wolves Lane 上的确切位置未知，锚点取该街道成交坐标的均值。可比 #4（0.496 英里）与被排除的 65 Perth Road（0.500 英里）接近临界，换用不同锚点可能反转。
6. **最佳可比刚好超出近期窗口。** 67 Wolves Lane（同街，3 卧，£672,000）成交于 12.7 个月前，故予标注并排除于估值集之外，而非以其主导估值——尽管它是现有物理上最可比的物业。
7. **2015 年标的成交无法经本接口核实**（84 个月上限；无门牌号）——见 §4。
