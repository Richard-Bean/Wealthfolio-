# -*- coding: utf-8 -*-
"""
nav_provider.py —— 最新净值与基金名称获取（数据源：天天基金公开接口）

接口说明（2026-09 实测可用，无需任何 key/登录）：
    https://fund.eastmoney.com/pingzhongdata/<基金代码>.js
返回一段 JS 变量定义，其中：
    fS_name             = 基金名称
    Data_netWorthTrend  = 历史单位净值数组
        [{"x": 毫秒时间戳, "y": 单位净值, ...}, ...]（按时间升序）

本模块只做两件事：
1. 下载该 JS 文本；
2. 用正则提取 fS_name 和 Data_netWorthTrend 的最后一个净值（最新净值）。
不执行任何 JS，解析规则肉眼可读，接口字段变化时只需改两处正则。

容错设计（保证主流程不因网络失败而中断）：
- 单只基金请求失败（超时/网络异常/解析失败）-> 返回 None；
- 调用方（scripts/run.py）对失败的基金自动降级为交割单确认净值，并在输出中提示。
- 全部基金批量拉取时按顺序串行，避免触发接口限流。
"""

import json
import re
import time
import urllib.request
from typing import Dict, Optional, Tuple

_API_TEMPLATE = "https://fund.eastmoney.com/pingzhongdata/{code}.js"
_TIMEOUT_SECONDS = 10
# 相邻请求间隔（秒），太频繁可能被限流
_REQUEST_INTERVAL = 0.3

# 两个正则：接口字段变化时优先检查这里
_NAME_RE = re.compile(r'fS_name\s*=\s*"([^"]*)"')
_TREND_RE = re.compile(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", re.S)


def fetch_one(code: str) -> Optional[Tuple[str, float, str]]:
    """
    获取单只基金的最新信息。

    返回:
        (基金名称, 最新单位净值, 净值日期) ；失败返回 None
    """
    url = _API_TEMPLATE.format(code=code)
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # 网络异常统一降级，不中断主流程
        print(f"[净值] {code} 请求失败（{exc.__class__.__name__}），将使用交割单净值兜底")
        return None

    name_match = _NAME_RE.search(text)
    trend_match = _TREND_RE.search(text)
    if not name_match or not trend_match:
        print(f"[净值] {code} 响应解析失败，将使用交割单净值兜底")
        return None

    try:
        trend = json.loads(trend_match.group(1))
        last = trend[-1]
        nav = float(last["y"])
        nav_date = time.strftime("%Y-%m-%d", time.localtime(last["x"] / 1000))
    except (ValueError, KeyError, IndexError):
        print(f"[净值] {code} 净值字段解析失败，将使用交割单净值兜底")
        return None

    return name_match.group(1), nav, nav_date


def fetch_batch(codes: list) -> Dict[str, Tuple[str, float, str]]:
    """
    批量获取多只基金信息；个别失败返回 None 条目，不整体中断。
    """
    result = {}
    for code in codes:
        info = fetch_one(code)
        if info:
            result[code] = info
        time.sleep(_REQUEST_INTERVAL)
    return result
