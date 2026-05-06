import io
import json
import re

import pandas as pd
import streamlit as st

from keyword_generator import Entity, KeywordGenerator
from pipeline import (
    CustomJsonSearchProvider,
    SearchRunner,
    SearchResult,
    SerperProvider,
    Step3Classifier,
    Step4Discoverer,
    Step4Input,
    Step5LLMJudge,
)
from step3_rules import (
    COMPETITOR_PATTERNS,
    CONSTRUCTION_PATTERNS,
    IRRELEVANT_PATTERNS,
    OFFICIAL_PATTERNS,
    THIRD_PARTY_PATTERNS,
)

st.set_page_config(page_title="Bid Discovery - Step1~4", layout="wide")

st.title("🚀 Bid Discovery（当前开发到 Step 4）")
st.caption("Step1 关键词 → Step2 搜索结果 → Step3 分类 → Step4 列表页发现（入口页仅下探1层）")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def infer_entity_type(name: str) -> str:
    lower_name = name.lower()
    if "school district" in lower_name or ("school" in lower_name and "district" in lower_name):
        return "school_district"
    if "county" in lower_name:
        return "county"
    if "city" in lower_name:
        return "city"
    if "university" in lower_name or "college" in lower_name:
        return "university"
    if "airport" in lower_name:
        return "airport_authority"
    if "housing authority" in lower_name:
        return "housing_authority"
    if "utility" in lower_name or "water district" in lower_name:
        return "utility"
    return "other_public_buyer"


def parse_file(uploaded_file) -> list[dict]:
    filename = uploaded_file.name.lower()
    if filename.endswith(".json"):
        data = json.load(uploaded_file)
        if not isinstance(data, list):
            raise ValueError("JSON 文件必须是数组 list")
        parsed = []
        for item in data:
            if isinstance(item, str):
                parsed.append({"name": item})
            elif isinstance(item, dict):
                parsed.append(item)
            else:
                raise ValueError("JSON 数组中的每一项必须是字符串或对象")
        return parsed

    df = pd.read_csv(uploaded_file) if filename.endswith(".csv") else pd.read_excel(uploaded_file)
    columns_lower = {c.lower(): c for c in df.columns}
    if "name" not in columns_lower and "entity_name" not in columns_lower:
        raise ValueError("文件必须包含 name 或 entity_name 列")
    return df.to_dict(orient="records")


def build_entities(raw_items: list[dict]) -> list[Entity]:
    entities: list[Entity] = []
    for i, item in enumerate(raw_items, start=1):
        name = item.get("entity_name") or item.get("name")
        if not name:
            continue
        name = normalize(name)
        if not name:
            continue

        entity_type = item.get("entity_type") or infer_entity_type(name)
        aliases = item.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [x.strip() for x in aliases.split(",") if x.strip()]
        elif not isinstance(aliases, list):
            aliases = []

        entities.append(
            Entity.from_dict(
                {
                    "id": item.get("id", i),
                    "entity_name": name,
                    "entity_type": entity_type,
                    "state_code": item.get("state_code"),
                    "state_name": item.get("state_name"),
                    "county_name": item.get("county_name"),
                    "city_name": item.get("city_name"),
                    "aliases": aliases,
                }
            )
        )
    return entities




def sanitize_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    # remove illegal control chars for openpyxl worksheet cells
    def _clean(v):
        if not isinstance(v, str):
            return v
        return "".join(ch for ch in v if (ch in {"\t", "\n", "\r"} or ord(ch) >= 32))

    # pandas>=2.1 recommends DataFrame.map for element-wise transforms;
    # keep applymap fallback for older versions.
    if hasattr(df, "map"):
        return df.map(_clean)
    return df.applymap(_clean)


def to_download_buttons(df: pd.DataFrame, key_prefix: str) -> None:
    safe_df = sanitize_for_excel(df)
    json_data = safe_df.to_json(orient="records", indent=2, force_ascii=False)
    csv_data = safe_df.to_csv(index=False)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        safe_df.to_excel(writer, index=False, sheet_name="data")
    col1, col2, col3 = st.columns(3)
    col1.download_button("下载 JSON", json_data, f"{key_prefix}.json", mime="application/json")
    col2.download_button("下载 CSV", csv_data, f"{key_prefix}.csv", mime="text/csv")
    col3.download_button(
        "下载 Excel",
        buffer.getvalue(),
        f"{key_prefix}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def parse_multiline_patterns(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def read_tabular_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".xlsx"):
        return sanitize_for_excel(pd.read_excel(uploaded_file))
    if name.endswith(".json"):
        return sanitize_for_excel(pd.DataFrame(json.load(uploaded_file)))
    # csv fallback encodings for production robustness
    raw = uploaded_file.getvalue()
    for enc in ["utf-8", "utf-8-sig", "gb18030", "big5", "latin1"]:
        try:
            return sanitize_for_excel(pd.read_csv(io.BytesIO(raw), encoding=enc))
        except Exception:
            continue
    # last resort with replacement to avoid pipeline break
    text = raw.decode("utf-8", errors="replace")
    return sanitize_for_excel(pd.read_csv(io.StringIO(text)))


def run_ai_entry_drilldown(candidates_df: pd.DataFrame, judge: Step5LLMJudge) -> list[str]:
    next_urls: list[str] = []
    blocked_terms = ["policy", "manual", "contact", "about", "faq", "news", "login"]
    for row in candidates_df.to_dict("records"):
        if str(row.get("candidate_type") or "") == "list_like":
            continue
        try:
            decision = judge.judge_entry_candidate(row)
        except Exception:
            continue
        if not decision.get("is_entry_page"):
            continue
        for u in decision.get("next_urls") or []:
            us = str(u).strip()
            lus = us.lower()
            if not (lus.startswith("http://") or lus.startswith("https://")):
                continue
            if any(t in lus for t in blocked_terms):
                continue
            if us and us not in next_urls:
                next_urls.append(us)
            if len(next_urls) >= 5:
                return next_urls
    return next_urls


def apply_step5_list_gate(
    list_pages_df: pd.DataFrame,
    judge: Step5LLMJudge,
    min_confidence: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use Step5 as final list-page gate: keep only rows judged as list_page with enough confidence."""
    if list_pages_df.empty:
        return list_pages_df, pd.DataFrame()
    list_pages_df = list_pages_df.copy()
    if "list_decision_source" not in list_pages_df.columns:
        list_pages_df["list_decision_source"] = "step4"
    decisions = judge.judge_rows(list_pages_df.to_dict("records"))
    step5_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in decisions]))
    if step5_df.empty:
        return list_pages_df.iloc[0:0], step5_df
    accepted = step5_df[
        (step5_df["final_type"].astype(str) == "list_page") &
        (pd.to_numeric(step5_df["confidence"], errors="coerce").fillna(0) >= min_confidence)
    ]
    if accepted.empty:
        return list_pages_df.iloc[0:0], step5_df
    accepted_urls = set(accepted["url"].astype(str).tolist())
    filtered = list_pages_df[list_pages_df["final_url"].astype(str).isin(accepted_urls)].copy()
    filtered = filtered.drop_duplicates(subset=["final_url"], keep="first").reset_index(drop=True)
    filtered["list_decision_source"] = "step5"
    return sanitize_for_excel(filtered), step5_df


def build_final_list_from_step5(
    list_pages_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    judge: Step5LLMJudge,
    min_confidence: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pool_frames: list[pd.DataFrame] = []
    if not candidates_df.empty:
        c = candidates_df.copy()
        if "candidate_type" in c.columns:
            c = c[c["candidate_type"].astype(str) != "entry_page"]
        pool_frames.append(c)
    if not list_pages_df.empty:
        l = list_pages_df.copy()
        if "confidence" in l.columns:
            l["confidence_num"] = pd.to_numeric(l["confidence"], errors="coerce").fillna(0)
            l = l[l["confidence_num"] >= 90]
            l = l.drop(columns=["confidence_num"])
        pool_frames.append(l)
    if not pool_frames:
        return pd.DataFrame(), pd.DataFrame()
    pool = pd.concat(pool_frames, ignore_index=True)
    if "final_url" in pool.columns and "url" not in pool.columns:
        pool["url"] = pool["final_url"]
    if "text" not in pool.columns:
        pool["text"] = ""
    pool = pool.drop_duplicates(subset=["url"], keep="first")
    decisions = judge.judge_rows(pool.to_dict("records"))
    step5_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in decisions]))
    if step5_df.empty:
        return pd.DataFrame(), step5_df
    accepted = step5_df[
        (step5_df["final_type"].astype(str) == "list_page")
        & (pd.to_numeric(step5_df["confidence"], errors="coerce").fillna(0) >= min_confidence)
    ].copy()
    if accepted.empty:
        return pd.DataFrame(), step5_df
    accepted = accepted.rename(columns={"url": "final_url"})
    accepted["list_decision_source"] = "step5"
    return sanitize_for_excel(accepted), step5_df


with st.sidebar:
    st.header("Step2 API 配置")
    provider_type = st.selectbox("搜索API类型", ["serper", "custom_json"], index=0)
    per_query_num = st.slider("每个query抓取结果数", min_value=3, max_value=20, value=10)
    enable_negative_terms = st.checkbox("Step1附加负关键词（-news 等）", value=False)

    if provider_type == "serper":
        serper_api_key = st.text_input("Serper API Key", type="password")
        serper_gl = st.text_input("Serper gl", value="us")
        serper_hl = st.text_input("Serper hl", value="en")
        custom_config = None
    else:
        serper_api_key = ""
        st.caption("自定义 API：支持 GET/POST + JSON 响应映射")
        endpoint = st.text_input("Endpoint URL")
        method = st.selectbox("Method", ["POST", "GET"], index=0)
        headers_json = st.text_area("Headers JSON", value='{"Content-Type":"application/json"}', height=100)
        body_template_json = st.text_area("Body Template JSON", value='{"q":"{query}","num":{num}}', height=120)
        results_path = st.text_input("Results path", value="organic")
        title_field = st.text_input("Title field", value="title")
        snippet_field = st.text_input("Snippet field", value="snippet")
        url_field = st.text_input("URL field", value="link")
        rank_field = st.text_input("Rank field", value="position")
        custom_config = {
            "endpoint": endpoint,
            "method": method,
            "headers_json": headers_json,
            "body_template_json": body_template_json,
            "results_path": results_path,
            "title_field": title_field,
            "snippet_field": snippet_field,
            "url_field": url_field,
            "rank_field": rank_field,
        }

    st.divider()
    st.header("Step3 域名规则（可编辑）")
    competitor_text = st.text_area("competitor", value="\n".join(COMPETITOR_PATTERNS), height=110)
    irrelevant_text = st.text_area("irrelevant", value="\n".join(IRRELEVANT_PATTERNS), height=110)
    third_party_text = st.text_area("third_party_platform", value="\n".join(THIRD_PARTY_PATTERNS), height=110)
    official_text = st.text_area("official_platform", value="\n".join(OFFICIAL_PATTERNS), height=110)
    construction_text = st.text_area("construction_platform", value="\n".join(CONSTRUCTION_PATTERNS), height=100)

    st.divider()
    st.header("Step4 输入设置")
    step4_source = st.radio("Step4 输入来源", options=["pass", "review", "pass+review"], index=2)

    st.divider()
    st.header("运行模式")
    run_mode = st.radio("选择流程", options=["full_pipeline", "step2_uploaded", "step4_only", "step5_only"], index=0)

    st.divider()
    st.header("Step5 模型配置")
    step5_provider = st.selectbox("Provider", ["deepseek", "qwen", "doubao", "openai_compatible"], index=0)
    step5_model = st.text_input("Model", value="deepseek-chat")
    step5_api_key = st.text_input("Step5 API Key", type="password")
    step5_base_url = st.text_input("Step5 Base URL", value="")
    step5_list_gate_threshold = st.slider("Step5 list gate threshold", min_value=0.0, max_value=1.0, value=0.6, step=0.05)

auto_run_step5 = run_mode == "full_pipeline"

if run_mode == "full_pipeline":
    uploaded_file = st.file_uploader("上传实体文件（json/csv/xlsx）", type=["json", "csv", "xlsx"])
    text_input = st.text_area("或粘贴实体（每行一个）", placeholder="City of Austin\nTravis County")
elif run_mode == "step2_uploaded":
    uploaded_file = st.file_uploader("上传 Step2 搜索结果文件（csv/xlsx/json）", type=["json", "csv", "xlsx"])
    text_input = ""
elif run_mode == "step4_only":
    uploaded_file = st.file_uploader("上传 Step4 输入文件（csv/xlsx/json）", type=["json", "csv", "xlsx"])
    text_input = ""
else:
    uploaded_file = st.file_uploader("上传 Step5 输入文件（csv/xlsx/json）", type=["json", "csv", "xlsx"])
    text_input = ""

if st.button("运行" if run_mode in {"step4_only", "step5_only"} else "运行 Step1 + Step2 + Step3 + Step4", type="primary"):
    raw_data: list[dict] = []
    try:
        if run_mode == "step5_only":
            if not uploaded_file:
                st.warning("请上传 Step5 输入文件")
                st.stop()
            df = read_tabular_file(uploaded_file)
            rows = df.to_dict("records")
            if not step5_api_key.strip():
                st.error("请填写 Step5 API Key")
                st.stop()
            judge = Step5LLMJudge(provider=step5_provider, model=step5_model, api_key=step5_api_key, base_url=step5_base_url)
            decisions = judge.judge_rows(rows)
            out_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in decisions]))
            st.success(f"Step5 完成：{len(out_df)} 条最终判定")
            st.dataframe(out_df, use_container_width=True, height=240)
            to_download_buttons(out_df, "step5_decisions")
            st.stop()

        if run_mode == "step2_uploaded":
            if not uploaded_file:
                st.warning("请上传 Step2 搜索结果文件")
                st.stop()
            df = read_tabular_file(uploaded_file)
            col_map = {c.lower(): c for c in df.columns}
            if "url" not in col_map:
                st.error("Step2 文件必须包含 url 列")
                st.stop()
            step2_results: list[SearchResult] = []
            for i, r in enumerate(df.to_dict("records"), start=1):
                step2_results.append(
                    SearchResult(
                        id=int(r.get(col_map.get("id", ""), i) or i),
                        entity_id=int(r.get(col_map.get("entity_id", ""), 1) or 1),
                        query_text=str(r.get(col_map.get("query_text", ""), "uploaded_step2") or "uploaded_step2"),
                        query_type=str(r.get(col_map.get("query_type", ""), "uploaded") or "uploaded"),
                        query_priority=int(r.get(col_map.get("query_priority", ""), 1) or 1),
                        rank=int(r.get(col_map.get("rank", ""), i) or i),
                        title=str(r.get(col_map.get("title", ""), "") or ""),
                        snippet=str(r.get(col_map.get("snippet", ""), "") or ""),
                        url=str(r.get(col_map["url"], "") or ""),
                        provider=str(r.get(col_map.get("provider", ""), "uploaded") or "uploaded"),
                    )
                )

            st.subheader("Step 2(上传) - 搜索结果")
            step2_df = pd.DataFrame([r.to_dict() for r in step2_results])
            st.dataframe(step2_df, use_container_width=True, height=220)
            to_download_buttons(step2_df, "step2_search_results_uploaded")

            st.subheader("Step 3 - pass/review/reject 分类")
            classifier = Step3Classifier(
                competitor_patterns=parse_multiline_patterns(competitor_text),
                irrelevant_patterns=parse_multiline_patterns(irrelevant_text),
                third_party_patterns=parse_multiline_patterns(third_party_text),
                official_patterns=parse_multiline_patterns(official_text),
                construction_patterns=parse_multiline_patterns(construction_text),
            )
            decisions = classifier.classify(step2_results)
            step3_df = pd.DataFrame([d.to_dict() for d in decisions])
            st.dataframe(step3_df, use_container_width=True, height=200)
            to_download_buttons(step3_df, "step3_decisions")

            result_set = {"pass"} if step4_source == "pass" else ({"review"} if step4_source == "review" else {"pass", "review"})
            decision_by_id = {int(x["id"]): x for x in step3_df.to_dict("records")}
            step4_inputs: list[Step4Input] = []
            for row in step2_results:
                d = decision_by_id.get(row.id)
                if not d or d["result"] not in result_set:
                    continue
                if d["type"] in {"third_party_platform", "official_platform", "construction_platform"}:
                    continue
                step4_inputs.append(Step4Input(id=row.id, url=row.url, step3_result=d["result"], step3_type=d["type"]))

            discoverer = Step4Discoverer(timeout=20.0, max_child_links=10)
            candidates = discoverer.discover_candidates(step4_inputs)
            list_pages, entry_pages = discoverer.discover(step4_inputs)
            candidates_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in candidates]))
            list_pages_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in list_pages]))
            if not list_pages_df.empty:
                list_pages_df["list_decision_source"] = "step4"
            entry_pages_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in entry_pages]))
            st.markdown("**step4_candidates.csv**")
            st.dataframe(candidates_df, use_container_width=True, height=220)
            to_download_buttons(candidates_df, "step4_candidates")
            if step5_api_key.strip():
                judge = Step5LLMJudge(provider=step5_provider, model=step5_model, api_key=step5_api_key, base_url=step5_base_url)
                list_pages_df, step5_gate_df = build_final_list_from_step5(
                    list_pages_df=list_pages_df,
                    candidates_df=candidates_df,
                    judge=judge,
                    min_confidence=step5_list_gate_threshold,
                )
                st.markdown("**step5_list_gate.csv**")
                st.dataframe(step5_gate_df, use_container_width=True, height=220)
                to_download_buttons(step5_gate_df, "step5_list_gate")
            if not list_pages_df.empty and "list_decision_source" in list_pages_df.columns:
                list_pages_df["list_decision_source"] = list_pages_df["list_decision_source"].fillna("step4")
            st.markdown("**list_pages.csv**")
            st.dataframe(list_pages_df, use_container_width=True, height=220)
            to_download_buttons(list_pages_df, "list_pages")
            st.markdown("**entry_pages.csv**")
            st.dataframe(entry_pages_df, use_container_width=True, height=220)
            to_download_buttons(entry_pages_df, "entry_pages")

            if step5_api_key.strip() and auto_run_step5:
                judge = Step5LLMJudge(provider=step5_provider, model=step5_model, api_key=step5_api_key, base_url=step5_base_url)
                decisions5 = judge.judge_rows(candidates_df.to_dict("records"))
                step5_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in decisions5]))
                st.markdown("**step5_decisions.csv**")
                st.dataframe(step5_df, use_container_width=True, height=220)
                to_download_buttons(step5_df, "step5_decisions")
            st.stop()

        if uploaded_file:
            raw_data.extend(parse_file(uploaded_file))
        if text_input.strip():
            raw_data.extend({"name": normalize(line)} for line in text_input.split("\n") if normalize(line))

        if not raw_data:
            st.warning("请输入实体数据")
            st.stop()

        if run_mode == "step4_only":
            if not uploaded_file:
                st.warning("请上传 Step4 输入文件")
                st.stop()
            df = read_tabular_file(uploaded_file)
            if "url" not in [c.lower() for c in df.columns]:
                st.error("Step4 输入必须包含 url 列")
                st.stop()
            col_map = {c.lower(): c for c in df.columns}
            urls = df[col_map["url"]].astype(str).tolist()
            step3_results = df[col_map["step3_result"]].astype(str).tolist() if "step3_result" in col_map else ["pass"] * len(urls)
            step3_types = df[col_map["step3_type"]].astype(str).tolist() if "step3_type" in col_map else ["other"] * len(urls)

            step4_inputs = [Step4Input(id=i + 1, url=u, step3_result=step3_results[i], step3_type=step3_types[i]) for i, u in enumerate(urls) if str(u).strip()]
            discoverer = Step4Discoverer(timeout=20.0, max_child_links=10)
            candidates = discoverer.discover_candidates(step4_inputs)
            list_pages, entry_pages = discoverer.discover(step4_inputs)

            candidates_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in candidates]))
            list_pages_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in list_pages]))
            if not list_pages_df.empty:
                list_pages_df["list_decision_source"] = "step4"
            entry_pages_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in entry_pages]))

            if step5_api_key.strip() and not candidates_df.empty:
                judge = Step5LLMJudge(provider=step5_provider, model=step5_model, api_key=step5_api_key, base_url=step5_base_url)
                next_urls = run_ai_entry_drilldown(candidates_df, judge)
                if next_urls:
                    drill_inputs = [Step4Input(id=100000 + i, url=u, step3_result="review", step3_type="other") for i, u in enumerate(next_urls)]
                    child_candidates = discoverer.discover_candidates(drill_inputs)
                    child_list, child_entry = discoverer.discover(drill_inputs)
                    if child_candidates:
                        candidates_df = pd.concat([candidates_df, pd.DataFrame([x.to_dict() for x in child_candidates])], ignore_index=True)
                    if child_list:
                        list_pages_df = pd.concat([list_pages_df, pd.DataFrame([x.to_dict() for x in child_list])], ignore_index=True)
                    if child_entry:
                        entry_pages_df = pd.concat([entry_pages_df, pd.DataFrame([x.to_dict() for x in child_entry])], ignore_index=True)


            if step5_api_key.strip():
                judge = Step5LLMJudge(provider=step5_provider, model=step5_model, api_key=step5_api_key, base_url=step5_base_url)
                list_pages_df, step5_gate_df = build_final_list_from_step5(
                    list_pages_df=list_pages_df,
                    candidates_df=candidates_df,
                    judge=judge,
                    min_confidence=step5_list_gate_threshold,
                )
                st.markdown("**step5_list_gate.csv**")
                st.dataframe(step5_gate_df, use_container_width=True, height=220)
                to_download_buttons(step5_gate_df, "step5_list_gate")

            if not list_pages_df.empty and "list_decision_source" in list_pages_df.columns:
                list_pages_df["list_decision_source"] = list_pages_df["list_decision_source"].fillna("step4")
            st.success(f"Step4 完成：候选页 {len(candidates_df)}，列表页 {len(list_pages_df)}，入口页 {len(entry_pages_df)}")
            st.markdown("**step4_candidates.csv**")
            st.dataframe(candidates_df, use_container_width=True, height=220)
            to_download_buttons(candidates_df, "step4_candidates")
            st.markdown("**list_pages.csv**")
            st.dataframe(list_pages_df, use_container_width=True, height=220)
            to_download_buttons(list_pages_df, "list_pages")
            st.markdown("**entry_pages.csv**")
            st.dataframe(entry_pages_df, use_container_width=True, height=220)
            to_download_buttons(entry_pages_df, "entry_pages")
            st.stop()

        entities = build_entities(raw_data)
        if not entities:
            st.warning("未解析出有效实体")
            st.stop()

        st.subheader("Step 1 - 关键词生成")
        generator = KeywordGenerator(enable_negative_terms=enable_negative_terms)
        step1_queries = generator.generate_queries_for_entities(entities)
        step1_df = pd.DataFrame([q.to_dict() for q in step1_queries])
        st.success(f"Step 1 完成：{len(step1_df)} 条查询")
        st.dataframe(step1_df, use_container_width=True, height=180)
        to_download_buttons(step1_df, "step1_queries")

        st.subheader("Step 2 - 搜索结果获取")
        if provider_type == "serper":
            provider = SerperProvider(api_key=serper_api_key, gl=serper_gl, hl=serper_hl)
        else:
            provider = CustomJsonSearchProvider(**custom_config)

        runner = SearchRunner(provider=provider)
        step2_results = runner.run_step2(step1_queries, per_query_num=per_query_num)
        step2_df = pd.DataFrame([r.to_dict() for r in step2_results])
        st.success(f"Step 2 完成：{len(step2_df)} 条搜索结果（按URL去重后）")
        st.dataframe(step2_df, use_container_width=True, height=220)
        to_download_buttons(step2_df, "step2_search_results")

        st.subheader("Step 3 - pass/review/reject 分类")
        classifier = Step3Classifier(
            competitor_patterns=parse_multiline_patterns(competitor_text),
            irrelevant_patterns=parse_multiline_patterns(irrelevant_text),
            third_party_patterns=parse_multiline_patterns(third_party_text),
            official_patterns=parse_multiline_patterns(official_text),
            construction_patterns=parse_multiline_patterns(construction_text),
        )
        decisions = classifier.classify(step2_results)
        step3_df = pd.DataFrame([d.to_dict() for d in decisions])
        st.success(f"Step 3 完成：{len(step3_df)} 条分类输出")
        st.dataframe(step3_df, use_container_width=True, height=200)
        to_download_buttons(step3_df, "step3_decisions")
        st.code(step3_df.to_json(orient="records", indent=2, force_ascii=False), language="json")

        st.subheader("Step 4 - 列表页发现（默认下探1层，条件命中可到2层）")
        result_set = {"pass"} if step4_source == "pass" else ({"review"} if step4_source == "review" else {"pass", "review"})

        decision_by_id = {int(x["id"]): x for x in step3_df.to_dict("records")}
        step4_inputs: list[Step4Input] = []
        for row in step2_results:
            d = decision_by_id.get(row.id)
            if not d:
                continue
            if d["result"] not in result_set:
                continue
            if d["type"] in {"third_party_platform", "official_platform", "construction_platform"}:
                continue  # Step4 先聚焦非平台域，降低噪音
            step4_inputs.append(Step4Input(id=row.id, url=row.url, step3_result=d["result"], step3_type=d["type"]))

        discoverer = Step4Discoverer(timeout=20.0, max_child_links=10)
        candidates = discoverer.discover_candidates(step4_inputs)
        list_pages, entry_pages = discoverer.discover(step4_inputs)

        candidates_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in candidates]))
        list_pages_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in list_pages]))
        if not list_pages_df.empty:
            list_pages_df["list_decision_source"] = "step4"
        entry_pages_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in entry_pages]))

        if step5_api_key.strip() and not candidates_df.empty:
            judge = Step5LLMJudge(provider=step5_provider, model=step5_model, api_key=step5_api_key, base_url=step5_base_url)
            next_urls = run_ai_entry_drilldown(candidates_df, judge)
            if next_urls:
                drill_inputs = [Step4Input(id=200000 + i, url=u, step3_result="review", step3_type="other") for i, u in enumerate(next_urls)]
                child_candidates = discoverer.discover_candidates(drill_inputs)
                child_list, child_entry = discoverer.discover(drill_inputs)
                if child_candidates:
                    candidates_df = pd.concat([candidates_df, pd.DataFrame([x.to_dict() for x in child_candidates])], ignore_index=True)
                if child_list:
                    list_pages_df = pd.concat([list_pages_df, pd.DataFrame([x.to_dict() for x in child_list])], ignore_index=True)
                if child_entry:
                    entry_pages_df = pd.concat([entry_pages_df, pd.DataFrame([x.to_dict() for x in child_entry])], ignore_index=True)

        if step5_api_key.strip():
            judge = Step5LLMJudge(provider=step5_provider, model=step5_model, api_key=step5_api_key, base_url=step5_base_url)
            list_pages_df, step5_gate_df = build_final_list_from_step5(
                list_pages_df=list_pages_df,
                candidates_df=candidates_df,
                judge=judge,
                min_confidence=step5_list_gate_threshold,
            )
            st.markdown("**step5_list_gate.csv**")
            st.dataframe(step5_gate_df, use_container_width=True, height=220)
            to_download_buttons(step5_gate_df, "step5_list_gate")

        if not list_pages_df.empty and "list_decision_source" in list_pages_df.columns:
            list_pages_df["list_decision_source"] = list_pages_df["list_decision_source"].fillna("step4")
        st.success(f"Step 4 完成：候选页 {len(candidates_df)}，列表页 {len(list_pages_df)}，入口页 {len(entry_pages_df)}")
        st.markdown("**step4_candidates.csv**")
        st.dataframe(candidates_df, use_container_width=True, height=220)
        to_download_buttons(candidates_df, "step4_candidates")

        st.markdown("**list_pages.csv**")
        st.dataframe(list_pages_df, use_container_width=True, height=220)
        to_download_buttons(list_pages_df, "list_pages")

        st.markdown("**entry_pages.csv**")
        st.dataframe(entry_pages_df, use_container_width=True, height=220)
        to_download_buttons(entry_pages_df, "entry_pages")

        if auto_run_step5:
            if not step5_api_key.strip():
                st.warning("默认自动运行 Step5，但未填写 API Key，已跳过")
            else:
                judge = Step5LLMJudge(provider=step5_provider, model=step5_model, api_key=step5_api_key, base_url=step5_base_url)
                step5_rows = candidates_df.to_dict("records") if not candidates_df.empty else list_pages_df.to_dict("records")
                decisions = judge.judge_rows(step5_rows)
                step5_df = sanitize_for_excel(pd.DataFrame([x.to_dict() for x in decisions]))
                st.subheader("Step 5 - 最终语义判定")
                st.success(f"Step 5 完成：{len(step5_df)} 条")
                st.dataframe(step5_df, use_container_width=True, height=220)
                to_download_buttons(step5_df, "step5_decisions")

    except Exception as exc:
        st.error(str(exc))
