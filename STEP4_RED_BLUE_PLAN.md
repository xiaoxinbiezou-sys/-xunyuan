# Step4 严格列表页识别方案（红蓝对抗 2 轮后定稿）

> 目标：Step4 必须“严出”，输出的 `list_page` 必须是真列表页；宁可降召回到 `entry/review`，也不把介绍页误报成列表页。

---

## 0. 判定口径（先统一标准）

`list_page` 必须同时满足：
1. 页面上存在**多条同构记录**（>=5 条）；
2. 每条记录中至少命中 2 个字段维度（如 title / due date / status / bid no / posted date）；
3. 具备至少 1 个“列表控制信号”（分页、筛选、排序、结果总数、表头列）；
4. 页面主要信息结构是“记录集合”，不是“说明文 + 少量推荐卡片”。

不满足上述任意一条，不得输出为 `list_page`，只能进入 `entry_page` / `multi_detail_hub` / `general_info`。

---

## 1. 红蓝对抗 Round 1

### 红方攻击 R1（误报路径）

1. **Featured/Highlights 模块伪装列表**
   - 首页带 3~6 条事件卡片，标题里有 Bid/RFP/date，易误判为列表。
2. **资源导航页伪装列表**
   - 大量链接 + procurement 关键词，但链接多为政策/指南/部门导航。
3. **供应商入口页伪装列表**
   - 有“Supplier Portal/Public Bid Site”按钮，但当前页并非列表。

### 蓝方防守 B1（第一轮修订）

1. 引入 `LIST_HARD_GATES`（硬门槛）
   - `record_count >= 5`
   - `record_schema_consistency >= 0.65`
   - `structured_fields_per_record_avg >= 2.0`
   - `has_list_controls == True`
   - 任一不满足：`NOT_LIST`。

2. 引入“伪列表降级规则”
   - 命中 `featured|highlights|latest|news|resources` 且无分页/筛选：降为 `entry` 或 `general_info`。

3. 引入“入口优先规则”
   - 命中 `view all|public bid site|bid opportunities|portal` 这种动作按钮，且当前记录数不足：优先 `entry_page`。

---

## 2. 红蓝对抗 Round 2

### 红方攻击 R2（漏报与误分）

1. **真实列表页无分页**
   - 某些小站只有 4~8 条记录，无分页；按 R1 会漏掉。
2. **多详情页聚合混淆**
   - 页面有很多项目条目，但每条是摘要+详情跳转，不是标准表格列表。
3. **入口页深一跳才能到列表**
   - 当前页只有按钮，需进入子页（甚至二跳）才到真正列表。

### 蓝方防守 B2（第二轮定稿）

1. 保持“严出 list”前提下的豁免机制（仅白名单域可用）
   - 若 `record_count in [4,8]` 且 `schema_consistency >= 0.8` 且 `field_coverage >= 0.75`，可判 `list_page`；
   - 否则不豁免。

2. 新增 `multi_detail_hub` 类型
   - 条目多，但字段结构不稳定、以 narrative 为主、缺列表控制 -> `multi_detail_hub`（不是 list）。

3. 下探策略升级为“1+条件2层”
   - 默认只下探1层；
   - 若命中强入口信号且未找到 list，可追加第2层（限定分支数与页面预算）；
   - 第二层仍需过 `LIST_HARD_GATES` 才能产出 list。

---

## 3. 最终决策流（严出版）

1. 先判 `hard_not_list`：
   - 单对象详情、纯介绍页、政策/指南长文、无记录集合 -> `general_info`。
2. 再判 `entry_page`：
   - 动作按钮强、当前页记录不足或结构不稳 -> `entry_page` 并下探。
3. 再判 `multi_detail_hub`：
   - 多条目但非结构化列表 -> `multi_detail_hub`。
4. 最后才判 `list_page`：
   - 必须通过 `LIST_HARD_GATES`（含豁免规则）。

**约束**：`list_page` 的 precision 优先级 > recall。

---

## 4. 针对你给的 4 类问题的定向修复映射

1. `procurement.ucop.edu` / `.../suppliers`
   - Featured/按钮页 -> `entry_page`；
   - 下探到 `.../event` 或 `publicRFx` 后再判 list。

2. `fiscal-partner-agencies`
   - 无采购动作链路 + 介绍语义强 -> `general_info`。

3. `suppliers.usc.edu/...bidding-opportunities`
   - 多项目但非标准列表 -> `multi_detail_hub`。

4. `thesupplierclearinghouse.com` / DGS how-to-business 页面
   - 介绍/指南页，不过 `LIST_HARD_GATES` -> `general_info`。

---

## 5. 可观测性（必须加）

每条 Step4 输出必须包含：
- `page_type`（list/entry/multi_detail/general_info）
- `list_gate_results`（每个硬门槛 pass/fail）
- `triggered_rules[]`
- `demotion_reason`（例如 `FEATURED_MODULE_NOT_FULL_LIST`）
- `drilldown_trace`（source -> child -> final）

没有这些字段，不允许上线“严出 list”策略。

---

## 6. 验收标准（上线前）

- List Precision >= 95%
- False List Rate（介绍页被判 list）<= 3%
- 你给的 4 类问题样本集准确率 100%
- 任一指标不达标：禁止切主。

---

## 7. 实施顺序（不改代码版）

1. 先加观测字段与离线评估脚本；
2. 再落地 `LIST_HARD_GATES` 与 `multi_detail_hub`；
3. 再落地下探“1+条件2层”；
4. 最后进行 AB 对照（旧/新 Step4 并跑）并按指标放量。
