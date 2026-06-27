"""
webhook 验签测试:密钥派生金标准(对照 QQ 官方 DEMO publicKey)+ 自签自验闭环 + 错误拒绝

作者: 李文煜
日期: 2026-06-25
"""
from qq.webhook import _derive_seed, _keypair, verify_signature


def test_derive_seed_matches_official_demo():
    """金标准:QQ 官方 DEMO secret=naOC...(28字符) 派生 seed 应为翻倍后前 32 字节"""
    seed = _derive_seed("naOC0ocQE3shWLAfffVLB1rhYPG7")
    # 官方 DEMO:seed = naOC0ocQE3shWLAfffVLB1rhYPG7naOC (原 28 字符 + 前 4 字符 = 32)
    assert seed == b"naOC0ocQE3shWLAfffVLB1rhYPG7naOC"


def test_publickey_matches_official_demo():
    """金标准:QQ 官方 DEMO 公钥(对照 sign.html DEMO publicKey 字节数组)"""
    pub, _ = _keypair("naOC0ocQE3shWLAfffVLB1rhYPG7")
    expected = bytes([215, 195, 98, 254, 120, 174, 248, 31, 242, 50, 135, 180, 147, 98, 139, 93,
                      176, 42, 60, 79, 227, 11, 33, 94, 77, 25, 96, 155, 93, 118, 103, 58])
    assert pub == expected


def test_verify_correct_signature(make_signature):
    """自签自验闭环:用同一 secret 私钥签名,公钥验证应通过"""
    body = b'{"op":0,"d":{"content":"hi"},"t":"C2C_MESSAGE_CREATE"}'
    sig = make_signature("1700000000", body)
    assert verify_signature("test-app-secret-1234567890abcdef", "1700000000", body, sig) is True


def test_verify_wrong_signature(make_signature):
    """错误签名应拒绝"""
    body = b'{"op":0}'
    sig = make_signature("1700000000", body)
    assert verify_signature("test-app-secret-1234567890abcdef", "1700000000", body, "00" * 64) is False
    # 篡改 body 后原签名失效
    assert verify_signature("test-app-secret-1234567890abcdef", "1700000000", body + b"x", sig) is False


def test_verify_wrong_secret(make_signature):
    """用不同 secret 派生的公钥验证应拒绝(防伪造)"""
    body = b'{"op":0}'
    sig = make_signature("1700000000", body, secret="test-app-secret-1234567890abcdef")
    assert verify_signature("wrong-secret-aaaaaaaaaaaaaaaaaa", "1700000000", body, sig) is False


def test_verify_invalid_hex():
    """非 hex 签名应拒绝(不抛异常)"""
    assert verify_signature("test-app-secret-1234567890abcdef", "1700000000", b"x", "not-hex") is False
