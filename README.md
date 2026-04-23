# 招投标线索发现（当前开发到 Step 4）

当前已完成：
1. **Step 1**：实体 -> 查询关键词。
2. **Step 2**：查询关键词 -> 搜索 API 结果（Serper + custom_json）。
3. **Step 3**：Google 结果 -> `pass / review / reject` + type。
4. **Step 4**：列表页发现（只做：列表页判定、入口页判定、入口页下探 1 层）。

## Step4 硬边界
- 不递归（最多一层）
- 不选“最佳页面”
- 不做 open/closed/award 语义分类
- 不处理第三方平台
- 不处理分页抓取
- 只输出列表页

## 安装

```bash
pip install -r requirements.txt
```

## 启动

```bash
streamlit run app.py
```

## 页面使用

1. 输入实体数据（文件或粘贴）。
2. 配置 Step2 搜索 API。
3. 调整 Step3 域名规则（支持增删）。
4. 在 Step4 选择输入来源：`pass` / `review` / `pass+review`。
5. 点击 `运行 Step1 + Step2 + Step3 + Step4`。

输出：
- `list_pages.csv`（source_url/final_url/discovered_from/parent_entry_url/title/status_code/confidence）
- `entry_pages.csv`（url/title/child_links_checked/list_pages_found_count）

## CLI（仅 Step1）

```bash
python keyword_generator.py --input entities.json --output step1_queries.json
python keyword_generator.py --input entities.json --output step1_queries.json --enable-negative-terms
```
