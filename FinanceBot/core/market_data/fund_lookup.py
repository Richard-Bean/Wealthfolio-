# -*- coding: utf-8 -*-
"""Resolve fund names to codes with strict local matching and API fallback."""

from __future__ import annotations

import csv
import difflib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


SEARCH_API = (
    "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
    "?m=1&key={key}"
)
LOCAL_FUZZY_THRESHOLD = 0.88
ONLINE_FUZZY_THRESHOLD = 0.82
ONLINE_SCORE_MARGIN = 0.05
QDII_OCR_RE = re.compile(r"QD.{0,4}?(?=[A-Ca-c人民币()（）]|$)", re.S)


@dataclass(frozen=True)
class FundCandidate:
    code: str
    name: str
    fund_company: str = ""
    source: str = "eastmoney_fund_search"


@dataclass(frozen=True)
class FundMatch:
    status: str
    code: str = ""
    matched_name: str = ""
    score: float = 0.0
    source: str = ""
    reason: str = ""
    candidates: list[dict] = field(default_factory=list)


def normalize_fund_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).upper()
    text = text.replace("IOO", "100").replace("LOO", "100")
    text = text.replace("蠃", "赢").replace("踹", "瑞")
    text = QDII_OCR_RE.sub("QDII", text)
    text = re.sub(r"(?<=[0-9])一(?=[0-9])", "-", text)
    text = re.sub(r"年一期", "年期", text)
    text = re.sub(r"基金|进阶理财|稳健理财|定投|金选|灵活取用|CNY", "", text)
    return "".join(char for char in text if char.isalnum())


def name_similarity(left: str, right: str) -> float:
    left_name = normalize_fund_name(left)
    right_name = normalize_fund_name(right)
    if not left_name or not right_name:
        return 0.0
    if left_name == right_name:
        return 1.0
    shorter, longer = sorted((left_name, right_name), key=len)
    if len(shorter) >= 6 and longer.startswith(shorter):
        return 0.92 + 0.08 * len(shorter) / len(longer)
    return difflib.SequenceMatcher(None, left_name, right_name).ratio()


def company_hint(name: str) -> str:
    normalized = normalize_fund_name(name)
    return normalized[:2]


def company_compatible(left: str, right: str) -> bool:
    return company_hint(left) == company_hint(right)


def share_class(name: str) -> str:
    normalized = normalize_fund_name(name)
    if normalized.endswith("C") or "C人民币" in normalized:
        return "C"
    if normalized.endswith("A") or "A人民币" in normalized:
        return "A"
    return ""


def currency_class(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(name))
    if "美元" in normalized or "USD" in normalized.upper():
        return "USD"
    return "CNY"


def candidate_compatible(query: str, candidate: FundCandidate) -> bool:
    if not company_compatible(query, candidate.name):
        return False
    query_share = share_class(query)
    candidate_share = share_class(candidate.name)
    if query_share and candidate_share and query_share != candidate_share:
        return False
    return currency_class(query) == currency_class(candidate.name)


def search_fund_by_name(query: str, timeout: int = 10) -> list[FundCandidate]:
    """Search public fund information by name. No account data is uploaded."""
    key = urllib.parse.quote(str(query))
    request = urllib.request.Request(
        SEARCH_API.format(key=key),
        headers={"User-Agent": "FinanceBot/1.0 local-fund-lookup"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="ignore")
    payload = json.loads(text)
    candidates = []
    for item in payload.get("Datas") or []:
        code = str(item.get("CODE") or item.get("_id") or "").strip()
        name = str(item.get("NAME") or "").strip()
        fund_company = str((item.get("FundBaseInfo") or {}).get("JJGS") or "").strip()
        if code and name:
            candidates.append(FundCandidate(code, name, fund_company))
    return candidates


def select_candidate(
    query: str,
    candidates: Iterable[FundCandidate],
) -> FundMatch:
    evaluated = [
        (name_similarity(query, candidate.name), candidate)
        for candidate in candidates
        if candidate_compatible(query, candidate)
    ]
    evaluated.sort(key=lambda item: item[0], reverse=True)
    candidate_rows = [
        {
            "code": candidate.code,
            "name": candidate.name,
            "fund_company": candidate.fund_company,
            "score": round(score, 4),
        }
        for score, candidate in evaluated[:5]
    ]
    if not evaluated:
        return FundMatch(
            status="pending",
            reason="API未返回同基金公司、同份额类别且同币种的候选",
            candidates=candidate_rows,
        )

    best_score, best = evaluated[0]
    second_score = evaluated[1][0] if len(evaluated) > 1 else 0.0
    if best_score < ONLINE_FUZZY_THRESHOLD:
        return FundMatch(
            status="pending",
            reason=f"API候选相似度过低: {best_score:.4f}",
            candidates=candidate_rows,
        )
    if best_score - second_score < ONLINE_SCORE_MARGIN:
        return FundMatch(
            status="pending",
            reason="API候选过于接近，需要人工确认",
            candidates=candidate_rows,
        )
    return FundMatch(
        status="resolved",
        code=best.code,
        matched_name=best.name,
        score=round(best_score, 4),
        source="eastmoney_fund_search",
        candidates=candidate_rows,
    )


def load_mapping(path: str | Path, legacy_path: str | Path | None = None) -> dict[str, str]:
    mapping: dict[str, str] = {}

    def add(name: str, code: str) -> None:
        if name and code:
            mapping[str(name).strip()] = str(code).strip()

    mapping_path = Path(path)
    if mapping_path.exists():
        with mapping_path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                add(row.get("标准基金名称", ""), row.get("基金代码", ""))
                add(row.get("OCR别名", ""), row.get("基金代码", ""))

    if legacy_path:
        legacy = Path(legacy_path)
        if legacy.exists():
            with legacy.open("r", encoding="utf-8-sig", newline="") as file:
                for row in csv.DictReader(file):
                    add(row.get("基金名称") or row.get("name", ""), row.get("基金代码") or row.get("symbol", ""))
    return mapping


def save_mapping_entry(
    path: str | Path,
    *,
    code: str,
    standard_name: str,
    ocr_alias: str,
    method: str,
    source: str,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["基金代码", "标准基金名称", "OCR别名", "匹配方式", "确认状态", "数据来源"]
    existing: list[dict] = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            existing = list(csv.DictReader(file))
    key = (str(code), str(ocr_alias).strip())
    if any((row.get("基金代码", ""), row.get("OCR别名", "").strip()) == key for row in existing):
        return
    existing.append({
        "基金代码": code,
        "标准基金名称": standard_name,
        "OCR别名": ocr_alias,
        "匹配方式": method,
        "确认状态": "confirmed" if method == "exact" else "auto",
        "数据来源": source,
    })
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing)


def resolve_fund_name(
    query: str,
    mapping: dict[str, str],
    *,
    lookup: Callable[[str], list[FundCandidate]] | None = None,
) -> FundMatch:
    local_candidates = []
    for name, code in mapping.items():
        candidate = FundCandidate(code, name, source="local_mapping")
        if not candidate_compatible(query, candidate):
            continue
        score = name_similarity(query, name)
        if score >= LOCAL_FUZZY_THRESHOLD:
            local_candidates.append((score, candidate))
    local_candidates.sort(key=lambda item: item[0], reverse=True)
    if local_candidates:
        score, candidate = local_candidates[0]
        return FundMatch(
            status="resolved",
            code=candidate.code,
            matched_name=candidate.name,
            score=round(score, 4),
            source="local_mapping",
        )

    if lookup is None:
        return FundMatch(status="pending", reason="本地没有高可信匹配，未启用API查询")
    return select_candidate(query, lookup(query))
