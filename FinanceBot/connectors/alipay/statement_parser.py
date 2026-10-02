# -*- coding: utf-8 -*-
"""
statement_parser.py —— 蚂蚁财富「基金交易明细」交割单 PDF 解析器

职责：把蚂蚁（杭州）基金销售有限公司出具的 PDF 交割单，解析为结构化的交易明细表。
输出为 pandas DataFrame，列如下（这是整个项目的数据标准格式）：

    确认日期 | 基金代码 | 基金名称 | 业务类型 | 申请金额 | 申请份额 | 确认金额 | 确认份额 | 手续费

解析依据（2026-09 实测蚂蚁财富交割单 22 页样例）：
- PDF 每页是一张 12 列表格，第一行是表头，数据行从第 2 行开始；
- 表头列顺序：订单号 | 交易时间 | 交易类型 | 基金名称 | 组合基金名称 | 基金代码 |
  申请金额 | 申请份额 | 确认金额 | 确认份额 | 手续费 | 确认日期
- 单元格内文本可能被换行拆散（如「南方纳斯\n达克\n100指数(QDII)A」），需要合并；
- 「申请份额」列对按金额申购显示为 "/"，按份额操作（卖出/转出）时为具体数值；
- 买卖方向由「申请份额/申请金额 哪个有数值」判断（详见 position_calculator.py）。

维护提示：若蚂蚁财富改版导致列顺序变化，只需调整本文件顶部的列索引映射，
下游（计算/导出/校验）不受影响。
"""

import re
from typing import List

import pandas as pd
import pdfplumber

# 输出列（项目内统一标准）
OUT_COLUMNS = [
    "确认日期", "基金代码", "基金名称", "业务类型",
    "申请金额", "申请份额", "确认金额", "确认份额", "手续费",
]

# PDF 12 列表格的列索引（0 起）
_IDX_ORDER_NO = 0
_IDX_TRADE_TIME = 1
_IDX_BIZ_TYPE = 2
_IDX_FUND_NAME = 3
_IDX_FUND_CODE = 5
_IDX_APPLY_AMOUNT = 6
_IDX_APPLY_SHARES = 7
_IDX_CONFIRM_AMOUNT = 8
_IDX_CONFIRM_SHARES = 9
_IDX_FEE = 10
_IDX_CONFIRM_DATE = 11

# 表头行标志：首列包含「订单号」即视为表头行（兼容多页重复表头）
_HEADER_MARK = "订单号"


def _clean_text(cell) -> str:
    """去掉单元格内的换行、空白，合并被拆散的文本（如基金名称）。"""
    if cell is None:
        return ""
    return str(cell).replace("\n", "").strip()


def _to_float(cell, default: float = 0.0) -> float:
    """字符串数字 -> float；"/"、空、异常值一律返回 default。"""
    s = _clean_text(cell).replace(",", "").replace("¥", "")
    if s in ("", "/", "-", "--"):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _to_date(cell) -> str:
    """
    蚂蚁交割单日期格式形如「2026/09/29 00:00」或「2026/09/24 11:05」，
    统一为「2026-09-29」；解析失败返回空串。
    """
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})", _clean_text(cell))
    if not m:
        return ""
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def parse_statement_pdf(pdf_path: str) -> pd.DataFrame:
    """
    解析蚂蚁财富交割单 PDF，返回标准明细 DataFrame。

    参数:
        pdf_path: PDF 文件路径（支持多页、跨页表格）
    返回:
        明细 DataFrame（列见 OUT_COLUMNS）；无有效数据时抛 ValueError
    """
    records: List[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table:
                    # 跳过空行与表头行
                    if not row or len(row) < 12:
                        continue
                    if _HEADER_MARK in _clean_text(row[_IDX_ORDER_NO]):
                        continue

                    biz_type = _clean_text(row[_IDX_BIZ_TYPE])
                    fund_code = _clean_text(row[_IDX_FUND_CODE])
                    # 业务类型和基金代码都为空 -> 不是数据行
                    if not biz_type or not fund_code:
                        continue

                    records.append({
                        "确认日期": _to_date(row[_IDX_CONFIRM_DATE]),
                        "基金代码": fund_code,
                        "基金名称": _clean_text(row[_IDX_FUND_NAME]),
                        "业务类型": biz_type,
                        "申请金额": _to_float(row[_IDX_APPLY_AMOUNT]),
                        "申请份额": _to_float(row[_IDX_APPLY_SHARES]),
                        "确认金额": _to_float(row[_IDX_CONFIRM_AMOUNT]),
                        "确认份额": _to_float(row[_IDX_CONFIRM_SHARES]),
                        "手续费": _to_float(row[_IDX_FEE]),
                    })

    if not records:
        raise ValueError(
            f"未从 {pdf_path} 解析到任何交易记录。"
            "请确认该 PDF 是蚂蚁财富基金交易明细交割单（12 列表格格式）。"
        )

    df = pd.DataFrame(records, columns=OUT_COLUMNS)
    # 有确认日期的按（基金代码, 确认日期）排序，便于后续逐笔记账
    df = df[df["确认日期"] != ""].sort_values(
        ["基金代码", "确认日期"], kind="mergesort"
    ).reset_index(drop=True)
    return df


if __name__ == "__main__":
    # 调试入口：python connectors/alipay/statement_parser.py <pdf路径>
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "../../data/raw/alipay/交割单.pdf"
    df = parse_statement_pdf(path)
    print(f"共 {len(df)} 笔交易")
    print(df.head(10).to_string(index=False))
