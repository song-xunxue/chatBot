"""
回调地址验证(op=13 握手)测试:签名金标准(对照 QQ 官方 DEMO signature)+ 路由回包

作者: 李文煜
日期: 2026-06-25
"""
from qq.webhook import sign_validation


def test_sign_validation_matches_official_demo():
    """金标准:QQ 官方 DEMO 回调验证签名(对照 event-emit.html DEMO)
    secret=DG5g3B4j9X2KOErG, plain_token=Arq0D5A61EgUu4OxUvOp, event_ts=1725442341"""
    sig = sign_validation("DG5g3B4j9X2KOErG", "1725442341", "Arq0D5A61EgUu4OxUvOp")
    expected = ("87befc99c42c651b3aac0278e71ada338433ae26fcb24307bdc5ad38c1adc2d0"
                "1bcfcadc0842edac85e85205028a1132afe09280305f13aa6909ffc2d652c706")
    assert sig == expected


def test_challenge_route_returns_plain_token_and_signature(api_client, fake_redis):
    """op=13 握手:无签名头也能处理(路由优先 op=13),回包含 plain_token + 正确 signature"""
    from fastapi.testclient import TestClient
    from main import app
    plain_token = "Arq0D5A61EgUu4OxUvOp"
    event_ts = "1725442341"
    body = {"op": 13, "d": {"plain_token": plain_token, "event_ts": event_ts}}
    with TestClient(app) as c:
        resp = c.post("/qq/webhook", json=body)  # 无 X-Signature 头
    assert resp.status_code == 200
    data = resp.json()
    assert data["plain_token"] == plain_token
    # 回包 signature 应等于本服务端用同 secret 私钥算出的签名
    assert data["signature"] == sign_validation("test-app-secret-1234567890abcdef", event_ts, plain_token)
