"""
llm/json_extract 单测(架构 #3 收口):从含噪 LLM 输出提取首个 JSON 对象/数组。
覆盖:纯净 / 前后噪声 / ```代码块包裹 / predicate 过滤(含 score 非数跳过)/ 无效输入 /
对象与数组并存时各自取首个 / 空串。

作者: 李文煜
日期: 2026-07-04
"""
from llm.json_extract import extract_json_array, extract_json_object


def test_object_clean():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_object_surrounding_noise():
    assert extract_json_object('好的,结果如下:\n{"score": 88, "reason": "好"}\n完毕') == {"score": 88, "reason": "好"}


def test_object_codeblock_wrapped():
    assert extract_json_object('```json\n{"name": "x"}\n```') == {"name": "x"}


def test_object_predicate_skips_nonmatching():
    # 无 predicate:取首个 dict
    obj = extract_json_object('{"reason": "无分"} {"score": 85}')
    assert obj == {"reason": "无分"}
    # 有 predicate(含 score):跳过首个取第二个
    obj2 = extract_json_object('{"reason": "无分"} {"score": 85}', predicate=lambda d: "score" in d)
    assert obj2 == {"score": 85}


def test_object_predicate_with_validity():
    # 模拟 _parse_score:含 score 但值非整数的对象要跳过,继续找合法的
    def valid_score(d):
        if "score" not in d:
            return False
        try:
            int(round(float(d["score"])))
            return True
        except (TypeError, ValueError):
            return False
    obj = extract_json_object('{"score": "高"} {"score": 85}', predicate=valid_score)
    assert obj == {"score": 85}


def test_object_skips_non_dict():
    # 首个 JSON 值是数组,仍应找到后面的对象
    assert extract_json_object('[1, 2] {"a": 1}') == {"a": 1}


def test_object_none_when_absent():
    assert extract_json_object("没有 json 在这里") is None


def test_array_clean():
    assert extract_json_array('[{"content": "a"}]') == [{"content": "a"}]


def test_array_surrounding_noise():
    assert extract_json_array('事实:\n[{"content": "x"}]\n done') == [{"content": "x"}]


def test_array_skips_non_list():
    # 首个 JSON 值是对象,仍应找到后面的数组
    assert extract_json_array('{"a": 1} [1, 2]') == [1, 2]


def test_array_none_when_absent():
    # 只有对象,无数组
    assert extract_json_array('{"a": 1}') is None


def test_empty_and_none():
    assert extract_json_object("") is None
    assert extract_json_array("") is None
