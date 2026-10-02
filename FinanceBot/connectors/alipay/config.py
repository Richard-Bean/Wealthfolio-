# -*- coding: utf-8 -*-
"""
config.py —— 支付宝连接器运行时配置

从仓库根 config/config.yaml 读取 connectors.alipay 段，并把相对路径换算成绝对路径。
对外暴露与旧 config.py 一致的属性：
    PDF_PATH / OUTPUT_DIR / ACCOUNT_NAME / FETCH_NAV / VERBOSE_NAV / find_input_pdf()
"""

import os

import yaml

# 仓库根 = 本文件所在目录向上三级（config.py -> alipay -> connectors -> 仓库根）
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_PATH = os.path.join(REPO_ROOT, "config", "config.yaml")


def _load_alipay_config() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("connectors", {}).get("alipay", {}) or {}


_ALIPAY = _load_alipay_config()
_input_dir = os.path.join(REPO_ROOT, _ALIPAY.get("input_dir", "data/raw/alipay"))
_output_dir = os.path.join(REPO_ROOT, _ALIPAY.get("output_dir", "data/processed/alipay"))
_default_pdf = _ALIPAY.get("default_pdf", "交割单.pdf")


def find_input_pdf() -> str:
    """
    自动查找输入目录下唯一的 PDF 交割单（不限定文件名）。
    - 目录里恰好一个 PDF -> 返回它的完整路径；
    - 没有或不止一个 -> 返回空字符串（由调用方回退到默认名或提示用户）。
    """
    if not os.path.isdir(_input_dir):
        return ""
    pdfs = [f for f in os.listdir(_input_dir) if f.lower().endswith(".pdf")]
    if len(pdfs) == 1:
        return os.path.join(_input_dir, pdfs[0])
    return ""


# 输入：优先自动识别目录下唯一 PDF；否则回退默认名「交割单.pdf」
PDF_PATH = find_input_pdf() or os.path.join(_input_dir, _default_pdf)

# 输出目录
OUTPUT_DIR = _output_dir

# Wealthfolio 导入时使用的账户名
ACCOUNT_NAME = _ALIPAY.get("account_name", "蚂蚁财富")

# 是否联网拉取最新净值（天天基金公开接口）
# True = 拉取最新净值/名称；False = 只用交割单确认净值，完全离线
FETCH_NAV = _ALIPAY.get("fetch_nav", True)

# 净值拉取失败时是否打印每只基金的降级提示
VERBOSE_NAV = _ALIPAY.get("verbose_nav", True)
