# -*- coding: utf-8 -*-
"""
config.py —— 全局配置

所有「可能想改」的参数都集中在这里，改配置即可，不必动业务代码。
路径均为项目根目录的相对路径，由本文件换算成绝对路径。
"""

import os


def find_input_pdf():
    """
    自动查找 data/input 目录下的 PDF 交割单（不限定文件名）。
    - 目录里恰好一个 PDF -> 返回它的完整路径；
    - 没有或不止一个 -> 返回空字符串（由调用方回退到默认名或提示用户）。
    这样把 PDF 丢进 data/input/ 即可，文件名随意。
    """
    input_dir = os.path.join(BASE_DIR, "data", "input")
    pdfs = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]
    if len(pdfs) == 1:
        return os.path.join(input_dir, pdfs[0])
    return ""


# 项目根目录（config.py 所在目录即项目根）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 输入：蚂蚁财富交割单 PDF。
# 优先自动识别 data/input 下唯一的 PDF（不管文件名）；
# 若 input 下没有或有多份 PDF，回退到默认名「交割单.pdf」。
PDF_PATH = find_input_pdf() or os.path.join(BASE_DIR, "data", "input", "交割单.pdf")

# 输出目录
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "output")

# Wealthfolio 导入时使用的账户名
ACCOUNT_NAME = "蚂蚁财富"

# 是否联网拉取最新净值（天天基金公开接口）
# True  = 拉取最新净值/名称；False = 只用交割单确认净值，完全离线
FETCH_NAV = True

# 净值拉取失败时是否打印每只基金的降级提示
VERBOSE_NAV = True
