from pathlib import Path

from core.market_data.fund_lookup import (
    FundCandidate,
    load_mapping,
    resolve_fund_name,
    save_mapping_entry,
    select_candidate,
)


def test_strict_local_match_does_not_map_different_fund_companies_to_same_code():
    mapping = {"国泰纳斯达克100指数(QDII)": "160213"}
    result = resolve_fund_name(
        "宝盈纳斯达克100指数(QDII)A",
        mapping,
        lookup=lambda _: [],
    )

    assert result.status == "pending"
    assert result.code == ""


def test_api_fallback_resolves_missing_fund_by_company_share_and_currency():
    candidates = [
        FundCandidate("019738", "宝盈纳斯达克100指数发起(QDII)A美元现汇", "宝盈基金"),
        FundCandidate("019736", "宝盈纳斯达克100指数发起(QDII)A人民币", "宝盈基金"),
        FundCandidate("019737", "宝盈纳斯达克100指数发起(QDII)C人民币", "宝盈基金"),
    ]
    result = resolve_fund_name(
        "宝盈纳斯达克100指数(QDII)A",
        {},
        lookup=lambda _: candidates,
    )

    assert result.status == "resolved"
    assert result.code == "019736"
    assert result.source == "eastmoney_fund_search"


def test_ambiguous_api_candidates_are_preserved_for_review():
    candidates = [
        FundCandidate("000001", "万家纳斯达克100指数优选(QDII)A人民币", "万家基金"),
        FundCandidate("000002", "万家纳斯达克100指数精选(QDII)A人民币", "万家基金"),
    ]

    result = select_candidate("万家纳斯达克100指数(QDII)A", candidates)

    assert result.status == "pending"
    assert result.code == ""
    assert len(result.candidates) == 2


def test_api_resolved_alias_is_saved_and_reused_locally():
    mapping_path = Path(__file__).with_name("_tmp_fund_mapping.csv")
    try:
        save_mapping_entry(
            mapping_path,
            code="019441",
            standard_name="万家纳斯达克100指数发起式(QDII)A",
            ocr_alias="万家纳斯达克100指数(QDII)A",
            method="online_api",
            source="test",
        )
        mapping = load_mapping(mapping_path)

        result = resolve_fund_name(
            "万家纳斯达克100指数(QDII)A",
            mapping,
            lookup=lambda _: [],
        )

        assert result.status == "resolved"
        assert result.code == "019441"
        assert result.source == "local_mapping"
    finally:
        mapping_path.unlink(missing_ok=True)
