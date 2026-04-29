from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from keyword_generator import GeneratedQuery, normalize_query_text
from step3_rules import (
    COMPETITOR_PATTERNS,
    CONSTRUCTION_PATTERNS,
    FILE_EXTENSIONS,
    GENERAL_TITLE_DESC_REJECT_TERMS,
    GENERAL_TITLE_PASS_TERMS,
    GENERAL_TITLE_REJECT_TERMS_GROUPS,
    GENERAL_TITLE_REVIEW_ONLY_TERMS,
    HIGH_INTENT_TITLE_PASS_TERMS,
    HIGH_INTENT_URL_PASS_TERMS,
    IRRELEVANT_PATTERNS,
    OFFICIAL_PATTERNS,
    THIRD_PARTY_PATTERNS,
    TYPE_ENUM,
    URL_REJECT_TERMS_GROUPS,
)

DUE_KEYWORDS = [
    "due date", "deadline", "closing date", "close date", "submission deadline", "bid due",
    "proposal due", "response due", "cutoff date",
]
POSTED_KEYWORDS = [
    "posted date", "date posted", "published date", "issued date", "release date", "advertised date",
]
OPEN_KEYWORDS = ["open date", "opening date", "start date"]

ENTRY_POSITIVE = [
    "bids", "open bids", "current bids", "solicitations", "opportunities", "rfp", "rfq", "contracts",
    "awards", "closed bids", "archive", "agencies", "vendors", "directory",
]
ENTRY_NEGATIVE = ["login", "register", "manual", "guide", "policy", "contact", "jobs", "news", "minutes", "agenda"]

DATE_REGEX_PATTERNS = [
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},\s+\d{4}\b", re.I),
]


@dataclass(slots=True)
class SearchResult:
    id: int
    entity_id: int
    query_text: str
    query_type: str
    query_priority: int
    rank: int
    title: str
    snippet: str
    url: str
    provider: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Step3Decision:
    id: int
    result: str
    type: str
    reason_codes: list[str] | None = None
    matched_pattern: str | None = None
    conflict: bool = False
    conflict_candidates: list[str] | None = None
    winner_rule_id: str | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        return payload


@dataclass(slots=True)
class Step4Input:
    id: int
    url: str
    step3_result: str
    step3_type: str


@dataclass(slots=True)
class ListPageRecord:
    source_url: str
    final_url: str
    discovered_from: str
    parent_entry_url: str
    title: str
    status_code: int
    confidence: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class EntryPageRecord:
    url: str
    title: str
    child_links_checked: int
    list_pages_found_count: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class PageFeatures:
    final_url: str
    title: str
    text: str
    links: list[tuple[str, str]]
    table_rows: int
    table_has_header: bool
    repeated_blocks: int
    titled_link_blocks: int
    date_count: int
    keyword_signal_count: int
    has_pagination: bool
    single_object: bool
    mostly_long_text: bool
    records_count: int


class SearchProvider(Protocol):
    provider_name: str

    def search(self, query: str, num: int = 10) -> list[dict]:
        ...


class SerperProvider:
    provider_name = "serper"

    def __init__(self, api_key: str, timeout: float = 20.0, gl: str = "us", hl: str = "en") -> None:
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.gl = gl
        self.hl = hl

    def search(self, query: str, num: int = 10) -> list[dict]:
        if not self.api_key:
            raise ValueError("Serper API key is required")

        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num, "gl": self.gl, "hl": self.hl},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("organic", []) or []


class CustomJsonSearchProvider:
    provider_name = "custom"

    def __init__(
        self,
        endpoint: str,
        method: str,
        headers_json: str,
        body_template_json: str,
        results_path: str,
        title_field: str,
        snippet_field: str,
        url_field: str,
        rank_field: str,
        timeout: float = 20.0,
    ) -> None:
        self.endpoint = endpoint.strip()
        self.method = method.upper().strip()
        self.headers = self._parse_json_obj(headers_json, "headers_json")
        self.body_template = self._parse_json_obj(body_template_json, "body_template_json")
        self.results_path = results_path.strip()
        self.title_field = title_field.strip()
        self.snippet_field = snippet_field.strip()
        self.url_field = url_field.strip()
        self.rank_field = rank_field.strip()
        self.timeout = timeout

    def search(self, query: str, num: int = 10) -> list[dict]:
        if not self.endpoint:
            raise ValueError("Custom API endpoint is required")
        if self.method not in {"GET", "POST"}:
            raise ValueError("Custom API method must be GET or POST")

        payload = self._render_payload(query=query, num=num)
        if self.method == "GET":
            resp = requests.get(self.endpoint, headers=self.headers, params=payload, timeout=self.timeout)
        else:
            resp = requests.post(self.endpoint, headers=self.headers, json=payload, timeout=self.timeout)

        resp.raise_for_status()
        data = resp.json()
        rows = _get_by_dot_path(data, self.results_path)
        if not isinstance(rows, list):
            raise ValueError(f"results_path '{self.results_path}' did not resolve to a list")

        out: list[dict] = []
        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            url = str(row.get(self.url_field) or "").strip()
            if not url:
                continue
            out.append(
                {
                    "title": str(row.get(self.title_field) or ""),
                    "snippet": str(row.get(self.snippet_field) or ""),
                    "link": url,
                    "position": int(row.get(self.rank_field) or idx),
                }
            )
        return out

    def _render_payload(self, query: str, num: int) -> dict[str, Any]:
        raw = json.dumps(self.body_template, ensure_ascii=False)
        rendered = raw.replace("{query}", query).replace("{num}", str(num))
        value = json.loads(rendered)
        if not isinstance(value, dict):
            raise ValueError("Rendered body payload must be JSON object")
        return value

    @staticmethod
    def _parse_json_obj(raw: str, field_name: str) -> dict[str, Any]:
        if not raw.strip():
            return {}
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{field_name} must be a JSON object")
        return value


class SearchRunner:
    def __init__(self, provider: SearchProvider) -> None:
        self.provider = provider

    def run_step2(self, queries: Iterable[GeneratedQuery], per_query_num: int = 10) -> list[SearchResult]:
        results: list[SearchResult] = []
        next_id = 1
        for query in queries:
            rows = self.provider.search(query.query_text, num=per_query_num)
            for row in rows:
                link = str(row.get("link") or "")
                if not link:
                    continue
                results.append(
                    SearchResult(
                        id=next_id,
                        entity_id=query.entity_id,
                        query_text=query.query_text,
                        query_type=query.query_type,
                        query_priority=query.priority_score,
                        rank=int(row.get("position") or next_id),
                        title=str(row.get("title") or ""),
                        snippet=str(row.get("snippet") or ""),
                        url=link,
                        provider=self.provider.provider_name,
                    )
                )
                next_id += 1
        return self._dedupe_search_results(results)

    @staticmethod
    def _dedupe_search_results(results: list[SearchResult]) -> list[SearchResult]:
        best: dict[str, SearchResult] = {}
        for item in results:
            key = normalize_query_text(item.url)
            prev = best.get(key)
            if prev is None or item.query_priority > prev.query_priority:
                best[key] = item
        deduped = list(best.values())
        deduped.sort(key=lambda x: x.id)
        return deduped


class Step3Classifier:
    def __init__(
        self,
        competitor_patterns: list[str] | None = None,
        irrelevant_patterns: list[str] | None = None,
        third_party_patterns: list[str] | None = None,
        official_patterns: list[str] | None = None,
        construction_patterns: list[str] | None = None,
    ) -> None:
        self.competitor_patterns = self._norm_list(competitor_patterns or COMPETITOR_PATTERNS)
        self.irrelevant_patterns = self._norm_list(irrelevant_patterns or IRRELEVANT_PATTERNS)
        self.third_party_patterns = self._norm_list(third_party_patterns or THIRD_PARTY_PATTERNS)
        self.official_patterns = self._norm_list(official_patterns or OFFICIAL_PATTERNS)
        self.construction_patterns = self._norm_list(construction_patterns or CONSTRUCTION_PATTERNS)

    def classify(self, rows: Iterable[SearchResult]) -> list[Step3Decision]:
        return [self.classify_one(row) for row in rows]

    def classify_one(self, row: SearchResult) -> Step3Decision:
        url = (row.url or "").strip().lower()
        title = (row.title or "").strip().lower()
        snippet = (row.snippet or "").strip().lower()
        path = (urlparse(url).path or "").lower()

        item_type, matched_pattern, conflict, conflict_candidates, winner_rule_id = self._resolve_type(url, title)
        if item_type not in TYPE_ENUM:
            item_type = "other"

        reason_codes: list[str] = []
        if self._is_file_url(path):
            reason_codes.append("HARD_REJECT_FILE")
            return Step3Decision(id=row.id, result="reject", type=item_type, reason_codes=reason_codes, matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)
        if item_type in {"competitor", "irrelevant"}:
            reason_codes.append(f"HARD_REJECT_{item_type.upper()}")
            return Step3Decision(id=row.id, result="reject", type=item_type, reason_codes=reason_codes, matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)

        login_like = self._contains_any(f"{url} {title} {snippet}", ["login", "sign in", "signin", "register", "registration", "supplier portal", "vendor self service", "vss", "public bid site"])
        if login_like:
            if item_type in {"official_platform", "third_party_platform", "construction_platform"}:
                reason_codes.append("LOGIN_PORTAL_REVIEW")
                return Step3Decision(id=row.id, result="review", type=item_type, reason_codes=reason_codes, matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)
            reason_codes.append("LOGIN_PORTAL_REVIEW_OTHER")
            return Step3Decision(id=row.id, result="review", type=item_type, reason_codes=reason_codes, matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)

        strong_irrelevant_terms = ["auction", "youtube", "youtu.be", "facebook", "instagram", "twitter", "x.com", "tiktok", "linkedin"]
        if self._contains_any(url, strong_irrelevant_terms):
            reason_codes.append("HARD_REJECT_STRONG_IRRELEVANT_URL")
            return Step3Decision(id=row.id, result="reject", type=item_type, reason_codes=reason_codes, matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)

        if item_type in {"third_party_platform", "official_platform"}:
            reason_codes.append("HARD_PASS_PLATFORM")
            return Step3Decision(id=row.id, result="pass", type=item_type, reason_codes=reason_codes, matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)
        if item_type == "construction_platform":
            reason_codes.append("CONSTRUCTION_REVIEW_DEFAULT")
            return Step3Decision(id=row.id, result="review", type=item_type, reason_codes=reason_codes, matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)

        high_intent = self._is_high_intent_domain(url)
        if high_intent:
            if self._contains_any(url, HIGH_INTENT_URL_PASS_TERMS):
                return Step3Decision(id=row.id, result="pass", type=item_type, reason_codes=["HIGH_INTENT_URL_PASS"], matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)
            if self._contains_any(title, HIGH_INTENT_TITLE_PASS_TERMS):
                return Step3Decision(id=row.id, result="pass", type=item_type, reason_codes=["HIGH_INTENT_TITLE_PASS"], matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)
            return Step3Decision(id=row.id, result="review", type=item_type, reason_codes=["HIGH_INTENT_REVIEW"], matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)

        if self._match_any(title, GENERAL_TITLE_REJECT_TERMS_GROUPS):
            return Step3Decision(id=row.id, result="review", type=item_type, reason_codes=["TITLE_REVIEW_FROM_REJECT_TERM"], matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)
        if self._contains_any(title, GENERAL_TITLE_DESC_REJECT_TERMS) or self._contains_any(snippet, GENERAL_TITLE_DESC_REJECT_TERMS):
            return Step3Decision(id=row.id, result="review", type=item_type, reason_codes=["DESC_REVIEW_FROM_REJECT_TERM"], matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)
        if self._contains_any(title, GENERAL_TITLE_PASS_TERMS):
            return Step3Decision(id=row.id, result="pass", type=item_type, reason_codes=["TITLE_PASS"], matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)
        if self._contains_any(title, GENERAL_TITLE_REVIEW_ONLY_TERMS):
            return Step3Decision(id=row.id, result="review", type=item_type, reason_codes=["TITLE_REVIEW"], matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)
        return Step3Decision(id=row.id, result="review", type=item_type, reason_codes=["DEFAULT_REVIEW"], matched_pattern=matched_pattern, conflict=conflict, conflict_candidates=conflict_candidates, winner_rule_id=winner_rule_id)

    def _resolve_type(self, url: str, title: str) -> tuple[str, str | None, bool, list[str], str | None]:
        hits: list[tuple[str, str]] = []
        for p in self.competitor_patterns:
            if self._match_pattern(url, p):
                hits.append(("competitor", p))
        for p in self.irrelevant_patterns:
            if self._match_pattern(url, p):
                hits.append(("irrelevant", p))
        for p in self.official_patterns:
            if self._match_pattern(url, p):
                hits.append(("official_platform", p))
        for p in self.third_party_patterns:
            if self._match_pattern(url, p):
                hits.append(("third_party_platform", p))
        for p in self.construction_patterns:
            if self._match_pattern(url, p):
                hits.append(("construction_platform", p))

        host = urlparse(url).netloc.lower().split(":")[0]
        path = (urlparse(url).path or "").lower()
        if host.endswith(".gov") or host.endswith(".mil"):
            hits.append(("official_platform", "suffix:.gov/.mil"))
        if host.endswith(".edu") and self._contains_any(f"{title} {path}", ["procurement", "purchasing", "bids", "contracts", "solicitations", "vendor", "sourcing"]):
            hits.append(("official_platform", "suffix:.edu+guard"))

        priority = ["competitor", "irrelevant", "official_platform", "third_party_platform", "construction_platform", "other"]
        conflict = len({h[0] for h in hits}) > 1
        if not hits:
            return "other", None, False, [], None
        winner = sorted(hits, key=lambda x: priority.index(x[0]))[0]
        return winner[0], winner[1], conflict, [f"{k}:{v}" for k, v in hits], f"priority:{winner[0]}"

    @staticmethod
    def _match_pattern(url: str, pattern: str) -> bool:
        return Step3Classifier._match_patterns(url, [pattern])

    @staticmethod
    def _is_file_url(path: str) -> bool:
        return any(path.endswith(ext) for ext in FILE_EXTENSIONS)

    @staticmethod
    def _is_high_intent_domain(url: str) -> bool:
        host = urlparse(url).netloc.lower().split(":")[0]
        return host.endswith(".gov") or host.endswith(".org") or host.endswith(".us") or host.endswith(".edu")

    @staticmethod
    def _contains_any(text: str, terms: list[str]) -> bool:
        t = text.lower()
        return any(term.lower() in t for term in terms)

    @staticmethod
    def _match_any(text: str, groups: list[list[str]]) -> bool:
        t = text.lower()
        for group in groups:
            if any(term.lower() in t for term in group):
                return True
        return False

    @staticmethod
    def _norm_list(values: list[str]) -> list[str]:
        return [v.strip().lower() for v in values if v.strip()]

    @staticmethod
    def _match_patterns(url: str, patterns: list[str]) -> bool:
        parsed = urlparse(url.lower())
        host = parsed.netloc.split(":")[0]
        host_path = f"{host}{parsed.path}"
        for pattern in patterns:
            p = pattern.lower()
            if "/" in p:
                if host_path.startswith(p) or p in host_path:
                    return True
            else:
                if host == p or host.endswith(f".{p}"):
                    return True
        return False


class Step4Discoverer:
    """严格列表页识别：优先保证 list_page 准确性；入口页可条件下探至2层。"""

    def __init__(self, timeout: float = 20.0, max_child_links: int = 10, max_depth: int = 2) -> None:
        self.timeout = timeout
        self.max_child_links = max_child_links
        self.max_depth = max_depth
        self.session = requests.Session()

    def discover(self, rows: Iterable[Step4Input]) -> tuple[list[ListPageRecord], list[EntryPageRecord]]:
        list_pages: list[ListPageRecord] = []
        entry_pages: list[EntryPageRecord] = []

        for row in rows:
            source_url = self.normalize_url(row.url)
            fetched = self.fetch(source_url)
            if fetched is None:
                continue
            final_url, status_code, html = fetched
            features = self.extract_features(final_url, html)

            is_list, confidence = self.is_list_page(features)
            if is_list:
                list_pages.append(
                    ListPageRecord(
                        source_url=source_url,
                        final_url=self.normalize_url(final_url),
                        discovered_from="direct",
                        parent_entry_url="",
                        title=features.title,
                        status_code=status_code,
                        confidence=confidence,
                    )
                )
                continue

            if not self.is_entry_page(features):
                continue

            candidates = self.select_candidate_links(final_url, features.links)
            found_count = 0
            for link in candidates:
                found_count += self._drill_for_list(
                    source_url=source_url,
                    parent_url=self.normalize_url(final_url),
                    link=link,
                    list_pages=list_pages,
                    depth=1,
                )

            entry_pages.append(
                EntryPageRecord(
                    url=self.normalize_url(final_url),
                    title=features.title,
                    child_links_checked=len(candidates),
                    list_pages_found_count=found_count,
                )
            )

        return self._dedupe_list_pages(list_pages), entry_pages


    def _drill_for_list(self, source_url: str, parent_url: str, link: str, list_pages: list[ListPageRecord], depth: int) -> int:
        fetched = self.fetch(link)
        if fetched is None:
            return 0
        final_url, status_code, html = fetched
        features = self.extract_features(final_url, html)
        is_list, conf = self.is_list_page(features)
        if is_list:
            list_pages.append(
                ListPageRecord(
                    source_url=source_url,
                    final_url=self.normalize_url(final_url),
                    discovered_from="entry_page" if depth == 1 else "entry_page_depth2",
                    parent_entry_url=parent_url,
                    title=features.title,
                    status_code=status_code,
                    confidence=conf,
                )
            )
            return 1
        if depth >= self.max_depth or not self._has_strong_entry_signal(features):
            return 0
        found = 0
        for sub in self.select_candidate_links(final_url, features.links)[:3]:
            found += self._drill_for_list(source_url, self.normalize_url(final_url), sub, list_pages, depth + 1)
        return found
    def fetch(self, url: str) -> tuple[str, int, str] | None:
        try:
            resp = self.session.get(url, timeout=self.timeout, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            return resp.url, resp.status_code, resp.text[:400000]
        except Exception:
            return None

    def extract_features(self, final_url: str, html: str) -> PageFeatures:
        soup = BeautifulSoup(html, "html.parser")
        title = (soup.title.get_text(" ", strip=True) if soup.title else "").strip()
        text = soup.get_text(" ", strip=True)

        links: list[tuple[str, str]] = []
        for a in soup.select("a[href]"):
            href = a.get("href") or ""
            full = urljoin(final_url, href)
            if urlparse(full).scheme not in {"http", "https"}:
                continue
            links.append((a.get_text(" ", strip=True), full))

        table_rows = 0
        table_has_header = False
        for table in soup.select("table"):
            rows = table.select("tr")
            if rows:
                table_rows = max(table_rows, len(rows) - 1)
            if table.select("th"):
                table_has_header = True

        repeated_blocks, titled_link_blocks = self._detect_repeated_blocks(soup)
        regex_dates = self._regex_date_count(text)
        keyword_dates = self._keyword_date_count(text)
        date_count = regex_dates + keyword_dates
        keyword_signal_count = sum(1 for k in ["due", "deadline", "posted", "status", "number"] if k in text.lower())

        has_pagination = bool(soup.select("a[href*='page='], a[aria-label*='page' i], .pagination"))
        records_count = max(table_rows, repeated_blocks, titled_link_blocks)

        long_text_nodes = sum(1 for p in soup.select("p") if len(p.get_text(" ", strip=True)) > 220)
        mostly_long_text = long_text_nodes >= 3 and records_count < 3

        single_object = records_count < 3 and len(soup.select("h1")) <= 1 and len(soup.select("article, .detail, .post")) >= 1

        return PageFeatures(
            final_url=final_url,
            title=title,
            text=text,
            links=links,
            table_rows=table_rows,
            table_has_header=table_has_header,
            repeated_blocks=repeated_blocks,
            titled_link_blocks=titled_link_blocks,
            date_count=date_count,
            keyword_signal_count=keyword_signal_count,
            has_pagination=has_pagination,
            single_object=single_object,
            mostly_long_text=mostly_long_text,
            records_count=records_count,
        )

    def is_list_page(self, f: PageFeatures) -> tuple[bool, int]:
        if f.single_object:
            return False, 0
        if f.records_count < 3 and f.table_rows < 3:
            return False, 0
        if f.mostly_long_text and f.records_count < 3:
            return False, 0

        text = f"{f.title} {f.text}".lower()
        featured_like = any(k in text for k in ["featured", "highlights", "latest", "news", "resources"])
        has_controls = f.has_pagination or f.table_has_header
        field_hits = sum(1 for k in ["due", "deadline", "posted", "status", "number", "solicitation", "rfp", "rfq"] if k in text)
        strict_records = f.records_count >= 5
        strict_structure = (f.table_rows >= 5) or (f.repeated_blocks >= 5 and f.titled_link_blocks >= 5) or (f.date_count >= 3 and f.records_count >= 5)

        if featured_like and not has_controls:
            return False, 20
        if not (strict_records and strict_structure and has_controls and field_hits >= 2):
            return False, 40

        score = 70
        if f.table_rows >= 8:
            score += 10
        if f.has_pagination:
            score += 10
        if f.date_count >= 5:
            score += 5
        return True, max(0, min(100, score))

    def is_entry_page(self, f: PageFeatures) -> bool:
        text = f"{f.title} {f.text}".lower()
        positive = 0
        for anchor_text, link in f.links:
            t = f"{anchor_text} {link}".lower()
            if any(n in t for n in ENTRY_NEGATIVE):
                continue
            if any(p in t for p in ENTRY_POSITIVE):
                positive += 1
            if positive >= 2:
                return True
        return any(p in text for p in ENTRY_POSITIVE)

    def _has_strong_entry_signal(self, f: PageFeatures) -> bool:
        text = f"{f.title} {f.text}".lower()
        return any(k in text for k in ["view all", "public bid site", "bid opportunities", "solicitations", "open bids", "vendor portal", "supplier portal"])

    def select_candidate_links(self, page_url: str, links: list[tuple[str, str]]) -> list[str]:
        base_host = urlparse(page_url).netloc.lower()
        selected: list[str] = []
        seen: set[str] = set()

        for text, href in links:
            u = self.normalize_url(href)
            host = urlparse(u).netloc.lower()
            if host != base_host:
                continue
            combo = f"{text} {u}".lower()
            if any(n in combo for n in ENTRY_NEGATIVE):
                continue
            if not any(p in combo for p in ENTRY_POSITIVE):
                continue
            if u in seen:
                continue
            seen.add(u)
            selected.append(u)
            if len(selected) >= self.max_child_links:
                break

        return selected

    @staticmethod
    def _detect_repeated_blocks(soup: BeautifulSoup) -> tuple[int, int]:
        counters: dict[str, int] = {}
        link_blocks = 0

        for el in soup.select("li, article, .card, .result, .item, tr"):
            txt = el.get_text(" ", strip=True)
            if len(txt) < 20:
                continue
            key = f"{el.name}:{' '.join(sorted(el.get('class', []))[:3])}"
            counters[key] = counters.get(key, 0) + 1
            a = el.select_one("a[href]")
            if a and len(a.get_text(" ", strip=True)) >= 4:
                link_blocks += 1

        repeated = max(counters.values()) if counters else 0
        return repeated, link_blocks

    @staticmethod
    def _regex_date_count(text: str) -> int:
        t = text.lower()
        total = 0
        for pattern in DATE_REGEX_PATTERNS:
            total += len(pattern.findall(t))
        return total

    @staticmethod
    def _keyword_date_count(text: str) -> int:
        t = " ".join(text.lower().split())
        count = 0
        for kw in DUE_KEYWORDS + POSTED_KEYWORDS + OPEN_KEYWORDS:
            if kw in t and ("date" in t or "time" in t):
                count += 1
        return count

    def normalize_url(self, url: str) -> str:
        parsed = urlparse(url.strip())
        query_items = []
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            lk = k.lower()
            if lk in {"page", "sort", "session", "sessionid"}:
                if lk == "page" and v not in {"1", ""}:
                    query_items.append((k, v))
                continue
            if lk.startswith("utm_"):
                continue
            query_items.append((k, v))
        query = urlencode(query_items, doseq=True)
        path = parsed.path.rstrip("/")
        normalized = urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))
        return normalized

    @staticmethod
    def _dedupe_list_pages(rows: list[ListPageRecord]) -> list[ListPageRecord]:
        best: dict[str, ListPageRecord] = {}
        for row in rows:
            key = normalize_query_text(row.final_url)
            prev = best.get(key)
            if prev is None or row.confidence > prev.confidence:
                best[key] = row
        return list(best.values())


def _get_by_dot_path(data: Any, path: str) -> Any:
    node = data
    for part in path.split("."):
        if not part:
            continue
        if isinstance(node, dict) and part in node:
            node = node[part]
            continue
        raise ValueError(f"Path not found: {path}")
    return node
