from pathlib import Path

from core.market_data.fund_lookup import (
    FundCandidate,
    load_mapping,
    normalize_fund_name,
    resolve_fund_name,
    save_mapping_entry,
    select_candidate,
    share_class,
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
    mapping_path = Path(__file__).with_name("临时基金名称代码映射.csv")
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



def test_ocr_confusables_and_truncated_names_resolve_to_local_mapping():
    mapping = {
        "永赢先锋半导体智选混合A": "025208",
        "华泰柏瑞南方东英恒生科技指数ETF联接(QDII)A": "015310",
        "广发中债7-10年期国开行债券指数A": "003376",
        "永赢科技智选混合A": "022364",
    }

    for query, code in [
        ("永蠃先锋半导体智选混合A", "025208"),
        ("华泰柏踹南方东英恒生科技指", "015310"),
        ("广发中债710年一期国开行债券", "003376"),
        ("永蠃科技智选混", "022364"),
    ]:
        result = resolve_fund_name(query, mapping, lookup=lambda _: [])
        assert result.status == "resolved"
        assert result.code == code
        assert result.source == "local_mapping"



def test_qdii_ocr_variants_normalize_and_keep_share_class():
    for name in [
        "华宝致远混合(QD围A",
        "华宝致远混合(QDΧA",
        "华宝致远混合(QDحI)A",
        "华宝致远混合(QDII)A",
    ]:
        normalized = normalize_fund_name(name)
        assert "QDII" in normalized
        assert share_class(name) == "A"

    assert share_class("华宝致远混合(QD围C") == "C"


def test_local_mapping_does_not_cross_a_and_c_share_classes():
    mapping = {
        "华宝致远混合(QDII)A": "008253",
        "华宝致远混合(QDII)C": "008254",
    }

    result = resolve_fund_name("华宝致远混合(QD围A", mapping, lookup=lambda _: [])

    assert result.status == "resolved"
    assert result.code == "008253"
