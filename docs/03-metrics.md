# M6 评价指标与公式 / Metrics & Formulas（v1，2026-11-08）

## 0. 符号 / Notation
- `p ∈ {1..8}` 名次；全局均值 4.5，标准差 σ ≈ 2.29
- `X` 任意组合（棋子×装备 / 棋子对 / 阵容…），`n(X)` 样本数
- `P̄(X)` 平均名次；`Top4(X)` 前四率；`Win(X)` 吃鸡率

## 1. 主/副指标 / Primary & Secondary
- **主指标**：平均名次 Δ（越负越好）；**副指标**：前四率 Δ；吃鸡率只展示不排序。

## 2. 基线与 Δ / Baselines
| 分析 | 基线 | 公式 |
|---|---|---|
| 棋子×装备 | 分层条件基线 | `Δ = P̄(u, star, lvl_bucket, item) − P̄(u, star, lvl_bucket)` |
| 棋子基线 | 全局 | `Δ = P̄(u, star) − 4.5` |
| 阵容 | 全局 | `Δ = P̄(comp) − 4.5` |
| 棋子共现 | 可加预期 | `Synergy(a,b) = P̄(a,b) − [P̄(a) + P̄(b) − 4.5]` |
| 羁绊档位 | 上一档 | `Δ = P̄(trait, k) − P̄(trait, k−1)` |

星级 1/2/3 分层；等级桶 `≤7 / 8 / 9+`；装备组合按单件、无序两件、三件分别计算。

## 3. 小样本防线 / Small-sample Guards
- 收缩：`P̂(X) = (n·P̄(X) + k·P_base) / (n + k)`，k = 30（默认）
- 区间：均值 `P̄ ± 1.96·σ/√n`（σ 用分层实测，缺省 2.29）；比例用 Wilson 95%
- 展示：`n<50` 不展示；`50≤n<200` 标"样本不足"；`n≥200` 标"可靠"
- **排序键 = 下置信界**：`score = −(P̂ + 1.96·σ/√n)`；不用人工 log(n) 权重

## 4. 混淆控制 / Confounding
- v1 分层（星级 × 等级桶 × 阶段桶）；v2 用 M5 模型 SHAP 作回归调整 Δ，两者并列，差异 > 0.3 名进入人工审查
- `rank_weight` 参数预留，默认关闭

## 5. 阶段强度代理 / Stage Proxy（实验性）
`EarlyPower(u, s) = freq(u | 淘汰于 s+1..s+2) / freq(u | 淘汰于 s)`，阶段桶 2 / 3 / 4 / 5 / 6+。
前端必须声明：仅基于被淘汰玩家终局棋盘，幸存者棋盘不可见。与 Track M 静态战力并列展示。

## 6. 机制轨战力 / Mechanistic Power
```
减伤(R)      = R / (100 + R)
EHP          = HP / (1 − w_phys·减伤(Armor) − w_mag·减伤(MR))
DPS_auto     = AD · AS · (1 + crit · (critMult − 1))
施法周期      = (Mana_max − Mana_init) / (10·AS + 受击回蓝率)
DPS_ability  = 技能伤害(star) · 命中目标数 / 施法周期
Power(u)     = (DPS_auto + DPS_ability) · EHP
ItemFit(u,i) = Power(u ⊕ i) / Power(u) − 1
```
阶段参数（w、命中目标数、对手典型数值）取自 Track S 的阶段典型棋盘。与 M4.2 统计 Δ 做 Spearman 对照，< 0.4 的棋子进入"机制遗漏"审查。

## 7. 克制矩阵 / Counter Matrix（Phase 2 末）
`Beat(A, B) = P(placement(A) < placement(B) | A, B 同局)`，依赖阵容聚类。

## 8. 数据边界 / Data Visibility
`tft-match-v1` **不含每回合胜负**；可见：`placement, level, last_round, time_eliminated, gold_left, total_damage_to_players, players_eliminated`。所有"阶段"指标均为代理。
