from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


QUERY_TYPES_BY_ENTITY_TYPE: dict[str, tuple[str, ...]] = {
    "state_agency": ("find_source", "find_listing", "find_awards", "find_vendor_portal"),
    "county": ("find_source", "find_listing", "find_awards", "find_vendor_portal"),
    "county_agency": ("find_source", "find_listing", "find_awards", "find_vendor_portal"),
    "city": ("find_source", "find_listing", "find_awards", "find_vendor_portal"),
    "city_agency": ("find_source", "find_listing", "find_awards", "find_vendor_portal"),
    "school_district": ("find_source", "find_listing", "find_vendor_portal"),
    "special_district": ("find_source", "find_listing", "find_awards", "find_vendor_portal"),
    "university": ("find_source", "find_listing", "find_vendor_portal"),
    "airport_authority": ("find_source", "find_listing", "find_awards", "find_vendor_portal"),
    "housing_authority": ("find_source", "find_listing", "find_awards", "find_vendor_portal"),
    "utility": ("find_source", "find_listing", "find_awards", "find_vendor_portal"),
    "other_public_buyer": ("find_source", "find_listing", "find_vendor_portal"),
}

QUERY_TEMPLATES: dict[str, tuple[tuple[str, str], ...]] = {
    "find_source": (
        ("source_procurement", "{name} procurement"),
        ("source_purchasing", "{name} purchasing"),
        ("source_purchasing_department", "{name} purchasing department"),
        ("source_procurement_department", "{name} procurement department"),
        ("source_bids", "{name} bids"),
        ("source_solicitations", "{name} solicitations"),
        ("source_contracts", "{name} contracts"),
        ("source_doing_business", "{name} doing business"),
    ),
    "find_listing": (
        ("listing_bid_opportunities", "{name} bid opportunities"),
        ("listing_open_bids", "{name} open bids"),
        ("listing_current_bids", "{name} current bids"),
        ("listing_open_solicitations", "{name} open solicitations"),
        ("listing_current_solicitations", "{name} current solicitations"),
        ("listing_procurement_opportunities", "{name} procurement opportunities"),
        ("listing_rfp", "{name} rfp"),
        ("listing_rfps", "{name} rfps"),
        ("listing_rfq", "{name} rfq"),
        ("listing_rfqs", "{name} rfqs"),
        ("listing_ifb", "{name} ifb"),
        ("listing_itb", "{name} itb"),
    ),
    "find_awards": (
        ("awards_contract_awards", "{name} contract awards"),
        ("awards_bid_results", "{name} bid results"),
        ("awards_awarded_contracts", "{name} awarded contracts"),
        ("awards_award_notices", "{name} award notices"),
        ("awards_closed_bids", "{name} closed bids"),
        ("awards_bid_tabs", "{name} bid tabulations"),
    ),
    "find_vendor_portal": (
        ("vendor_vendor_portal", "{name} vendor portal"),
        ("vendor_supplier_portal", "{name} supplier portal"),
        ("vendor_vendor_registration", "{name} vendor registration"),
        ("vendor_supplier_registration", "{name} supplier registration"),
        ("vendor_doing_business", "{name} doing business with us"),
    ),
}

NEGATIVE_TERMS_BY_QUERY_TYPE: dict[str, tuple[str, ...]] = {
    "find_source": ("-jobs", "-careers", "-news", "-blog", "-guide", "-manual"),
    "find_listing": ("-jobs", "-careers", "-news", "-blog", "-guide", "-manual", "-how"),
    "find_awards": ("-jobs", "-careers", "-news", "-blog", "-guide", "-manual"),
    "find_vendor_portal": ("-jobs", "-careers", "-news", "-blog"),
}


@dataclass(slots=True)
class Entity:
    id: int
    entity_name: str
    entity_type: str
    state_code: str | None = None
    state_name: str | None = None
    county_name: str | None = None
    city_name: str | None = None
    aliases: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Entity":
        aliases = data.get("aliases") or []
        if not isinstance(aliases, list):
            raise TypeError("aliases must be a list[str]")

        return cls(
            id=int(data["id"]),
            entity_name=str(data["entity_name"]),
            entity_type=str(data["entity_type"]),
            state_code=_clean_optional_string(data.get("state_code")),
            state_name=_clean_optional_string(data.get("state_name")),
            county_name=_clean_optional_string(data.get("county_name")),
            city_name=_clean_optional_string(data.get("city_name")),
            aliases=[str(a) for a in aliases if _clean_optional_string(a)],
        )


@dataclass(slots=True)
class GeneratedQuery:
    entity_id: int
    query_text: str
    query_type: str
    priority_score: int
    template_name: str
    name_variant: str
    negative_terms: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class KeywordGenerator:
    def __init__(self, enable_negative_terms: bool = False) -> None:
        self.templates = QUERY_TEMPLATES
        self.query_types_by_entity_type = QUERY_TYPES_BY_ENTITY_TYPE
        self.enable_negative_terms = enable_negative_terms

    def build_name_variants(self, entity: Entity) -> list[str]:
        variants: list[str] = []
        seen: set[str] = set()

        def add(value: str | None) -> None:
            cleaned = _normalize_spaces(value)
            if not cleaned:
                return
            dedupe_key = cleaned.casefold()
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            variants.append(cleaned)

        base_name = entity.entity_name
        add(base_name)

        for alias in entity.aliases:
            add(alias)

        stripped = self._strip_prefix(base_name)
        if stripped != base_name:
            add(stripped)

        for variant in list(variants):
            if "-" in variant:
                add(variant.replace("-", " "))

        for variant in list(variants):
            if entity.state_name:
                add(f"{variant} {entity.state_name}")
            if entity.state_code:
                add(f"{variant} {entity.state_code}")

        return variants

    def generate_queries(self, entity: Entity) -> list[GeneratedQuery]:
        allowed_query_types = self.query_types_by_entity_type.get(entity.entity_type)
        if not allowed_query_types:
            raise ValueError(f"Unsupported entity_type: {entity.entity_type}")

        name_variants = self.build_name_variants(entity)
        generated: list[GeneratedQuery] = []
        seen: set[str] = set()

        for query_type in allowed_query_types:
            templates = self.templates[query_type]
            negative_terms = list(NEGATIVE_TERMS_BY_QUERY_TYPE.get(query_type, ()))

            for name_variant in name_variants:
                for template_name, template in templates:
                    base_query = _normalize_spaces(template.format(name=name_variant))
                    query_text = self._attach_negative_terms(base_query, negative_terms)

                    dedupe_key = normalize_query_text(query_text)
                    if dedupe_key in seen:
                        continue

                    seen.add(dedupe_key)
                    generated.append(
                        GeneratedQuery(
                            entity_id=entity.id,
                            query_text=query_text,
                            query_type=query_type,
                            priority_score=priority_score_query(base_query, query_type),
                            template_name=template_name,
                            name_variant=name_variant,
                            negative_terms=negative_terms if self.enable_negative_terms else [],
                        )
                    )

        return generated

    def generate_queries_for_entities(self, entities: Iterable[Entity]) -> list[GeneratedQuery]:
        all_queries: list[GeneratedQuery] = []
        for entity in entities:
            all_queries.extend(self.generate_queries(entity))
        return all_queries

    def _attach_negative_terms(self, base_query: str, negative_terms: Sequence[str]) -> str:
        if not self.enable_negative_terms or not negative_terms:
            return base_query
        return _normalize_spaces(f"{base_query} {' '.join(negative_terms)}")

    @staticmethod
    def _strip_prefix(name: str) -> str:
        for prefix in ("City of ", "County of ", "Town of ", "Village of ", "Board of "):
            if name.startswith(prefix):
                return name[len(prefix) :].strip()
        return name


class QueryRepository:
    """预留数据库持久化接口，后续可替换为 MySQL 实现。"""

    def save_queries(self, queries: Sequence[GeneratedQuery]) -> int:
        raise NotImplementedError("Implement with your database adapter when needed.")


def _clean_optional_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = _normalize_spaces(str(value))
    return cleaned or None


def _normalize_spaces(text: str | None) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def normalize_query_text(text: str) -> str:
    return _normalize_spaces(text).casefold()


def priority_score_query(query_text: str, query_type: str) -> int:
    normalized = normalize_query_text(query_text)

    if any(
        keyword in normalized
        for keyword in (
            " bid opportunities",
            " open bids",
            " current bids",
            " open solicitations",
            " current solicitations",
            " procurement opportunities",
            " procurement",
            " purchasing",
        )
    ):
        return 95

    if any(
        keyword in normalized
        for keyword in (
            " awarded contracts",
            " contract awards",
            " award notices",
            " bid results",
            " closed bids",
            " bid tabulations",
            " contracts",
            " solicitations",
        )
    ):
        return 85

    if any(keyword in normalized for keyword in (" rfp", " rfps", " rfq", " rfqs", " ifb", " itb")):
        return 78

    if any(
        keyword in normalized
        for keyword in (" vendor portal", " supplier portal", " vendor registration", " supplier registration")
    ):
        return 72

    fallback_scores = {
        "find_source": 88,
        "find_listing": 90,
        "find_awards": 82,
        "find_vendor_portal": 70,
    }
    return fallback_scores.get(query_type, 70)


def load_entities_from_json(path: str | Path) -> list[Entity]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Input JSON must be a list of entity objects")
    return [Entity.from_dict(item) for item in raw]


def save_queries_to_json(path: str | Path, queries: Sequence[GeneratedQuery]) -> None:
    payload = [query.to_dict() for query in queries]
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate official-source-oriented search queries for public procurement source discovery."
    )
    parser.add_argument("--input", required=True, help="Path to input entities JSON file")
    parser.add_argument("--output", required=True, help="Path to output queries JSON file")
    parser.add_argument(
        "--enable-negative-terms",
        action="store_true",
        help="Append negative terms like -news -blog to generated queries",
    )
    args = parser.parse_args()

    generator = KeywordGenerator(enable_negative_terms=args.enable_negative_terms)
    entities = load_entities_from_json(args.input)
    queries = generator.generate_queries_for_entities(entities)
    save_queries_to_json(args.output, queries)

    print(f"Loaded {len(entities)} entities")
    print(f"Generated {len(queries)} queries")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
