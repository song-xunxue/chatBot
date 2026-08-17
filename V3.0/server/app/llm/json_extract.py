"""
LLM 输出容错 JSON 解析(架构收口 #3,2026-07-04)
LLM 常把 JSON 夹在解释文字 / ```代码块 / 前后噪声里。本 module 统一"从含噪文本提取首个 JSON 值",
消除此前 score._parse_score / reverse_infer._parse_json_object / encoder._parse_facts /
tool_loop 内联 json.loads 四处同构独立实现(改一处格式约定要改 4 处,无 locality)。

- extract_json_object:首个 dict,可选 predicate 过滤(如要求含 'score' 键且值可转整数)
- extract_json_array:首个 list

均用 raw_decode 从每个 '{'/'[' 尝试解析,容忍前后多余文本/嵌套/代码块包裹;找不到返 None。
predicate 让调用方保留各自的领域过滤(如 score 跳过"含 score 但非数"的对象继续扫描)。

作者: 李文煜
日期: 2026-07-04
"""
import json
from collections.abc import Callable


def _iter_json_values(text: str, marker: str):
    """扫描 text,从每个 marker('{'/('[')处 raw_decode,产出成功解析的 JSON 值(生成器)。
    raw_decode 只消费一个完整 JSON 值的前缀,故容忍尾随噪声。"""
    decoder = json.JSONDecoder()
    s = text or ""
    for i, ch in enumerate(s):
        if ch != marker:
            continue
        try:
            obj, _ = decoder.raw_decode(s[i:])
        except json.JSONDecodeError:
            continue
        yield obj


def extract_json_object(text: str,
                        predicate: Callable[[dict], bool] | None = None) -> dict | None:
    """从 LLM 输出提取首个 JSON 对象(dict)。可选 predicate 过滤(如要求含某键)。
    非对象值跳过;无匹配返 None。predicate 让调用方保留领域过滤(如跳过非法 score 继续扫描)。"""
    for obj in _iter_json_values(text, "{"):
        if isinstance(obj, dict) and (predicate is None or predicate(obj)):
            return obj
    return None


def extract_json_array(text: str) -> list | None:
    """从 LLM 输出提取首个 JSON 数组(list)。非数组值跳过;无返 None。"""
    for obj in _iter_json_values(text, "["):
        if isinstance(obj, list):
            return obj
    return None
