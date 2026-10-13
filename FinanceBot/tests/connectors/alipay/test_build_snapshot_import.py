# -*- coding: utf-8 -*-

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "connectors" / "alipay" / "scripts"))

from build_snapshot_import import (  # noqa: E402
    DEFAULT_ACCOUNT,
    normalize_account_name,
    validate_screenshot_row,
)


def test_build_import_uses_antfortune_account_name():
    assert DEFAULT_ACCOUNT == "蚂蚁财富"
    assert normalize_account_name("蚂蚁财富——测试B") == "蚂蚁财富"


def test_rate_mismatch_blocks_export_by_default():
    with pytest.raises(ValueError, match="需要人工复核"):
        validate_screenshot_row(
            "019736",
            "宝盈纳斯达克100指数(QDII)A",
            20.09,
            0.09,
            0.45,
            ocr_rate_pct=0.95,
        )


def test_corroborated_rate_warning_can_export():
    validate_screenshot_row(
        "019736",
        "宝盈纳斯达克100指数(QDII)A",
        20.09,
        0.09,
        0.45,
        ocr_rate_pct=0.95,
        allow_rate_warning=True,
    )


def test_invalid_cost_still_blocks_even_with_rate_warning():
    with pytest.raises(ValueError, match="invalid_cost_basis"):
        validate_screenshot_row(
            "016452",
            "南方纳斯达克100指数(QDII)A",
            611.80,
            700.00,
            2.03,
            ocr_rate_pct=2.03,
            allow_rate_warning=True,
        )
