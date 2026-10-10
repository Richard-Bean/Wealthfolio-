# -*- coding: utf-8 -*-
"""
nav_cache.py —— 基金公开净值获取与本地缓存

数据源：
    https://fund.eastmoney.com/pingzhongdata/<基金代码>.js

隐私边界：
- 请求 URL 只包含基金代码，不上传持仓截图、金额、收益、账户或个人身份信息；
- 服务端仍可能记录 IP、访问时间和请求的基金代码；
- 因此本模块默认低频、串行访问，并把结果持久化到本地 JSON。

可靠性设计：
- 单只基金失败不会破坏已有缓存；
- 缓存采用同目录临时文件 + os.replace 原子替换；
- `latest_nav_asof()` 可按截图时间选择“当时已结算的最新净值”。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.request import Request, urlopen

_API_TEMPLATE = "https://fund.eastmoney.com/pingzhongdata/{code}.js"
_NAME_RE = re.compile(r'fS_name\s*=\s*"([^"]*)"')
_TREND_RE = re.compile(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", re.S)
_TIMEOUT_SECONDS = 10
_REQUEST_INTERVAL_SECONDS = 0.3
_HISTORY_LIMIT = 60
_SOURCE_NAME = "eastmoney_pingzhongdata"


def _fetch_history(code: str) -> Dict:
    url = _API_TEMPLATE.format(code=code)
    request = Request(url, headers={"User-Agent": "FinanceBot/1.0 local-nav-cache"})
    with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        text = response.read().decode("utf-8", errors="ignore")

    name_match = _NAME_RE.search(text)
    trend_match = _TREND_RE.search(text)
    if not name_match or not trend_match:
        raise ValueError(f"{code}: 响应缺少 fS_name 或 Data_netWorthTrend")

    raw_history = json.loads(trend_match.group(1))
    history: List[Dict] = []
    for item in raw_history:
        timestamp = item.get("x")
        nav = item.get("y")
        if timestamp is None or nav is None:
            continue
        history.append({
            "date": time.strftime("%Y-%m-%d", time.localtime(float(timestamp) / 1000)),
            "nav": float(nav),
        })

    if not history:
        raise ValueError(f"{code}: 没有可用净值记录")

    history = history[-_HISTORY_LIMIT:]
    return {
        "code": code,
        "name": name_match.group(1),
        "latest_date": history[-1]["date"],
        "latest_nav": history[-1]["nav"],
        "history": history,
    }


def update_cache(
    codes: Iterable[str],
    cache_path: str | Path,
    *,
    retries: int = 2,
    retry_delay: float = 1.0,
) -> Dict:
    """批量更新本地净值缓存。失败的基金保留旧值并记录错误。"""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_cache(path)
    funds = dict(current.get("funds", {}))
    errors = dict(current.get("errors", {}))

    for code in dict.fromkeys(codes):
        last_error = None
        for attempt in range(retries + 1):
            try:
                funds[code] = _fetch_history(code)
                errors.pop(code, None)
                last_error = None
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < retries:
                    time.sleep(retry_delay * (attempt + 1))
        if last_error:
            errors[code] = last_error
        time.sleep(_REQUEST_INTERVAL_SECONDS)

    payload = {
        "source": _SOURCE_NAME,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "funds": funds,
        "errors": errors,
    }
    _atomic_write_json(path, payload)
    return payload


def load_cache(cache_path: str | Path) -> Dict:
    path = Path(cache_path)
    if not path.exists():
        return {"source": _SOURCE_NAME, "updated_at": None, "funds": {}, "errors": {}}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def latest_nav_asof(
    cache: Dict,
    code: str,
    as_of: datetime | date,
    *,
    settlement_hour: int = 20,
) -> Optional[Dict]:
    """
    返回指定时点已经可见的最新净值。

    规则：
    - 净值日期不能晚于 as_of 日期；
    - 如果 as_of 是截图当天且时间早于 settlement_hour，则不使用当天净值，
      因为截图时当天净值通常尚未结算发布；
    - 返回 {date, nav}，找不到返回 None。
    """
    fund = cache.get("funds", {}).get(code)
    if not fund:
        return None

    if isinstance(as_of, datetime):
        as_of_date = as_of.date()
        exclude_same_day = as_of.hour < settlement_hour
    else:
        as_of_date = as_of
        exclude_same_day = False

    candidates = [
        item for item in fund.get("history", [])
        if date.fromisoformat(item["date"]) <= as_of_date
        and not (exclude_same_day and item["date"] == as_of_date.isoformat())
    ]
    return candidates[-1] if candidates else None


def _atomic_write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
