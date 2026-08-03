"""
QQ REST 消息发送(httpx)
封装发私聊(C2C)消息:走「被动回复」(带 msg_id),60 分钟窗口内有效、不耗主动消息月配额。

接口(查 QQ 文档「发送消息」确认):
  POST {api_base}/v2/users/{openid}/messages
  header: Authorization: QQBot {access_token}
  body:   {"content":..., "msg_type":0(文本), "msg_id":...(被动回复必带), "msg_seq":...(防同 msg_id 重复)}

M1 echo 链路:webhook 收 C2C_MESSAGE_CREATE → send_c2c_message(openid, "收到:xxx", msg_id=...)。
M2 起真实回复由 pipeline 产出;主动消息(无 msg_id,耗月配额)留 M8 代人聊天。

作者: 李文煜
日期: 2026-06-25

2026-06-25
变更说明：
  1. M1 创建 api_client:send_c2c_message(被动回复,带 msg_id/msg_seq)+ httpx 单例

2026-08-04
变更说明：
  1. M-tts 新增 upload_c2c_file + send_c2c_voice:上传 silk 语音(file_type=3 base64)→ 发 msg_type=7 富媒体语音消息
"""
import logging

import httpx

from core.config import settings
from qq.auth import get_access_token
from qq.reply_guard import sanitize_reply

logger = logging.getLogger(__name__)

# httpx 异步单例(与 auth._client 分离:不同 base_url;复用连接池;测试 monkeypatch 注入 MockTransport)
_client: httpx.AsyncClient | None = None


async def init_client() -> None:
    """lifespan 启动时创建 httpx 异步客户端单例(base_url 指向 QQ 消息 API)"""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0)


async def close_client() -> None:
    """lifespan 关闭时释放 httpx 客户端"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def send_c2c_message(openid: str, content: str, *, msg_id: str = "", msg_seq: int = 1,
                           human_authored: bool = False) -> dict:
    """发私聊消息(被动回复优先:带 msg_id 不耗主动月配额,60 分钟窗口内有效)

    参数:
        openid:  QQ 用户 openid(事件 d.author.user_openid)
        content: 文本内容
        msg_id:  用户消息 id(被动回复必填;留空则成主动消息,耗月配额,M8 代人聊天用)
        msg_seq: 回复序号,与 msg_id 联用防同 msg_id 重复发送(QQ 规则:相同 msg_id+msg_seq 重复会失败)
        human_authored: True=content 是人类手打(如 Web 面板代答),**跳过出站守卫**;
            False(默认)= 机器产出(LLM/stream/tool-loop),先过 sanitize_reply 再发。
            出站守卫(架构 #3)作为本 send 缝隙的不变量:机器产出的错误文本(429/堆栈/内部URL)
            绝不流到 QQ 用户;新调用方默认受保护,人类文本显式 opt-out(避免误伤合法 admin 文本)。
    返回:
        QQ 响应 {"id": 消息id, "timestamp": 发送时间}
    """
    assert _client is not None, "httpx client 未初始化,请在 lifespan 调 init_client"
    # 出站守卫:机器产出默认过守卫;human_authored=True(如 admin 手打代答)显式跳过
    if not human_authored:
        content = sanitize_reply(content)
    token = await get_access_token()
    headers = {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}
    payload: dict = {"content": content, "msg_type": 0, "msg_seq": msg_seq}
    if msg_id:
        payload["msg_id"] = msg_id  # 被动回复(回复类),窗口 60min
    resp = await _client.post(f"{settings.qq_api_base}/v2/users/{openid}/messages",
                              headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()


async def send_download(url: str) -> bytes:
    """下载 QQ 附件(图片等)原始 bytes。QQ 附件 CDN URL 需鉴权(QQBot access_token)。
    M-vision:M2.6 图片消息解析时调,失败抛异常由调用方(webhook._describe_image)软失败兜底。"""
    assert _client is not None, "httpx client 未初始化,请在 lifespan 调 init_client"
    token = await get_access_token()
    headers = {"Authorization": f"QQBot {token}"}
    resp = await _client.get(url, headers=headers, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


# 媒体文件类型(QQ /v2/users/{openid}/files 的 file_type 取值;对照 AstrBot VOICE_FILE_TYPE=3)
FILE_TYPE_IMAGE = 1
FILE_TYPE_VIDEO = 2
FILE_TYPE_VOICE = 3   # 语音(silk 格式)
FILE_TYPE_FILE = 4


async def upload_c2c_file(openid: str, file_type: int, file_data_b64: str,
                          *, srv_send_msg: bool = False) -> dict:
    """上传 C2C 私聊媒体文件,拿 file_info(发富媒体消息用)。M-tts 2026-08-04。

    POST /v2/users/{openid}/files,file_data = 整个文件的 base64 字符串(非 URL,非 multipart)。
    srv_send_msg=False(默认)=仅上传不发送(本项目走被动回复路径,单独调 send_c2c_voice,不占主动配额)。
    timeout 调大 30s(base64 长语音 body 膨胀;虽 silk 通常几十 KB,留余量)。

    返回:{file_uuid, file_info(opaque,发消息原样回传), ttl}(ttl 过期需重传,故上传后立即发)。
    """
    assert _client is not None, "httpx client 未初始化,请在 lifespan 调 init_client"
    token = await get_access_token()
    headers = {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}
    payload = {"file_type": file_type, "file_data": file_data_b64, "srv_send_msg": srv_send_msg}
    resp = await _client.post(f"{settings.qq_api_base}/v2/users/{openid}/files",
                              headers=headers, json=payload, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


async def send_c2c_voice(openid: str, file_info: str, *, msg_id: str = "",
                         msg_seq: int = 1, content: str = "") -> dict:
    """发 C2C 语音消息(msg_type=7 富媒体 + media.file_info)。M-tts 2026-08-04。

    复用 send_c2c_message 的 msg_id/msg_seq 被动回复机制(语音占每消息 4 次回复预算之一)。
    file_info 来自 upload_c2c_file 返回(有 ttl,上传后立即发)。
    不过 sanitize_reply(语音是音频非文本,无错误文本泄漏风险)。

    参数:
        file_info: upload_c2c_file 返回的 file_info
        msg_id: 被动回复必填(留空=主动消息,耗月配额)
        msg_seq: 防同 msg_id 重复(递增,与文本分段复用同一 msg_seq 序列)
        content: 可选附文(通常留空,纯语音)
    返回:QQ 响应 {id, timestamp}。
    """
    assert _client is not None, "httpx client 未初始化,请在 lifespan 调 init_client"
    token = await get_access_token()
    headers = {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}
    payload: dict = {
        "msg_type": 7,                        # 7=富媒体(图片/语音/视频/文件统一)
        "media": {"file_info": file_info},
        "msg_seq": msg_seq,
    }
    if msg_id:
        payload["msg_id"] = msg_id            # 被动回复(60min 窗口)
    if content:
        payload["content"] = content          # 附文(默认空=纯语音)
    resp = await _client.post(f"{settings.qq_api_base}/v2/users/{openid}/messages",
                              headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()

