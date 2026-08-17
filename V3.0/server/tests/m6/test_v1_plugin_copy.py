"""
V1.0 收敛插件(time_aware / reply_enhance)纯函数单测。

作者: 李文煜
日期: 2026-06-28
"""
from plugins.time_aware.plugin import time_of_day, season_label
from plugins.reply_enhance.plugin import should_flush, merge_output


def test_time_of_day():
    assert time_of_day(8) == "清晨"
    assert time_of_day(10) == "上午"
    assert time_of_day(12) == "中午"
    assert time_of_day(15) == "下午"
    assert time_of_day(20) == "晚上"
    assert time_of_day(23) == "深夜"


def test_season_label():
    assert season_label(1) == "冬"
    assert season_label(5) == "春"
    assert season_label(7) == "夏"
    assert season_label(10) == "秋"


def test_should_flush():
    assert should_flush([], 3) is True                      # 空缓冲
    assert should_flush([{"text": "x"}] * 3, 3) is True     # 达上限
    assert should_flush([{"text": "你好。"}], 3) is True    # 句末标点(语义完整)
    assert should_flush([{"text": "嗯"}], 3) is False       # 未达上限、无标点


def test_merge_output():
    assert merge_output("  hi  ") == "hi"
    assert merge_output("a\n\n\n\nb") == "a\n\nb"           # 3+ 换行合并为 2
    assert merge_output("x", merge_blank=False) == "x"
    assert merge_output("") == ""
