"""
TTS 语音 REST 接口(M-tts,2026-08-04):音色试听 + 自定义音色(声音克隆)管理。
克隆走硅基流动 zero-shot(上传参考音频→uri→当 voice 用),无需本地 GPU。

路由(prefix /api/v1):
  POST /tts/preview                音色试听(固定文本→mp3;预设/克隆 uri 均可)
  POST /tts/voice/upload           上传参考音频克隆(音频或视频;视频 ffmpeg 提取)→ uri
  GET  /tts/voice/list             列已克隆音色(代理硅基流动)
  POST /tts/voice/delete           删除克隆音色 {uri}
  GET  /tts/voice/active?object_id 设当前音色回显
  PUT  /tts/voice/active           设/清当前音色(克隆 uri;清=回退预设)

作者: 李文煜
日期: 2026-08-04
"""
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from api._auth import verify_token
from core.config import settings
from modality.silk import find_ffmpeg
from modality.tts import (
    HEARTBEAT_KEY, HEARTBEAT_TTL, TTS_VOICES, check_gptsovits_status, get_tts,
)
from storage.redis_client import get_redis

router = APIRouter(prefix="/api/v1", tags=["tts"])

_SILI = "https://api.siliconflow.cn/v1"
PREVIEW_TEXT = "夫君，今天辛苦啦，早点休息哦。"
_VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".m4v", ".wmv")
_K_ACTIVE = "mychat:tts:custom_voice:{oid}"


def _is_video(filename: str) -> bool:
    return any(filename.lower().endswith(e) for e in _VIDEO_EXT)


async def _extract_audio_clip(video_bytes: bytes, start_sec: float, dur_sec: float) -> bytes:
    """ffmpeg 从视频提取音频(可选截取 [start, start+dur])→ mp3 bytes(44.1k 单声道)。
    克隆参考音频要求 mp3/wav;视频上传时本函数转 mp3。"""
    ff = find_ffmpeg()
    tmpdir = tempfile.mkdtemp(prefix="tts_video_")
    vin = Path(tmpdir) / "v.in"
    vout = Path(tmpdir) / "a.mp3"
    try:
        vin.write_bytes(video_bytes)
        cmd = [ff, "-y", "-i", str(vin), "-hide_banner"]
        if start_sec > 0:
            cmd += ["-ss", str(start_sec)]      # 起始秒(定位片段)
        if dur_sec > 0:
            cmd += ["-t", str(dur_sec)]         # 取 dur 秒(克隆参考 8-10s 最佳)
        cmd += ["-vn", "-acodec", "libmp3lame", "-ar", "44100", "-ac", "1", str(vout)]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg 提取音频失败: {stderr.decode(errors='replace')[-400:]}")
        out = vout.read_bytes()
        if not out:
            raise RuntimeError("ffmpeg 提取音频为空(视频无音轨?)")
        return out
    finally:
        for f in (vin, vout):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


# ================ 音色试听 ================

@router.post("/tts/preview", dependencies=[Depends(verify_token)])
async def preview_tts(body: dict = Body(...)):
    """音色试听:给定 voice 合成预览文本 → mp3。voice 可为预设名(claire/...)或克隆 uri(speech:...)。"""
    voice = str(body.get("voice", "")).strip()
    is_clone_uri = voice.startswith("speech:")
    if not is_clone_uri and voice not in TTS_VOICES:
        raise HTTPException(status_code=400, detail=f"无效音色,预设可选: {list(TTS_VOICES.keys())},或克隆 uri(speech:...)")
    text = str(body.get("text") or PREVIEW_TEXT)
    try:
        mp3 = await get_tts().synthesize(text, voice)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"TTS 合成失败: {e}")
    if not mp3:
        raise HTTPException(status_code=503, detail="TTS 未配置(无 SILICONFLOW_API_KEY),无法预览")
    return Response(content=mp3, media_type="audio/mpeg")


# ================ 克隆音色管理(代理硅基流动)================

@router.post("/tts/voice/upload", dependencies=[Depends(verify_token)])
async def upload_voice(file: UploadFile = File(...), customName: str = Form(...),
                       text: str = Form(""), start_sec: float = Form(0), dur_sec: float = Form(0)):
    """上传参考音频克隆音色。音频直接用;视频 ffmpeg 提取(可选 start_sec/dur_sec 截片段)。
    返回 {uri, customName}。403=账号未实名(克隆硬门槛)。"""
    key = settings.siliconflow_api_key
    if not key:
        raise HTTPException(status_code=503, detail="无 SILICONFLOW_API_KEY")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="空文件")
    fname = file.filename or ""
    try:
        if _is_video(fname):
            audio_bytes = await _extract_audio_clip(raw, start_sec, dur_sec)
        else:
            audio_bytes = raw
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 上传硅基流动(multipart:model/customName/text/file)
    files = {"file": ("voice.mp3", audio_bytes, "audio/mpeg")}
    data = {"model": settings.tts_model, "customName": customName, "text": text}
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(f"{_SILI}/uploads/audio/voice",
                         headers={"Authorization": f"Bearer {key}"}, data=data, files=files)
    if r.status_code == 403:
        raise HTTPException(status_code=403, detail="账号未实名认证,无法使用克隆音色")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"上传失败: {r.text[:200]}")
    uri = r.json().get("uri")
    if not uri:
        raise HTTPException(status_code=502, detail=f"上传未返 uri: {r.text[:200]}")
    return {"uri": uri, "customName": customName}


@router.get("/tts/voice/list", dependencies=[Depends(verify_token)])
async def list_voices():
    """列已克隆音色(代理硅基流动 GET /audio/voice/list)"""
    key = settings.siliconflow_api_key
    if not key:
        raise HTTPException(status_code=503, detail="无 SILICONFLOW_API_KEY")
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{_SILI}/audio/voice/list", headers={"Authorization": f"Bearer {key}"})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"列表失败: {r.text[:200]}")
    return r.json()  # {result: [{model, customName, text, uri}, ...]}


@router.post("/tts/voice/delete", dependencies=[Depends(verify_token)])
async def delete_voice(body: dict = Body(...)):
    """删除克隆音色 {uri}。若该 uri 是当前活跃音色,一并清除(回退预设)。"""
    uri = str(body.get("uri", "")).strip()
    if not uri:
        raise HTTPException(status_code=400, detail="uri required")
    key = settings.siliconflow_api_key
    if not key:
        raise HTTPException(status_code=503, detail="无 SILICONFLOW_API_KEY")
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{_SILI}/audio/voice/deletions",
                         headers={"Authorization": f"Bearer {key}"}, json={"uri": uri})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"删除失败: {r.text[:200]}")
    return {"deleted": uri}


@router.get("/tts/voice/active", dependencies=[Depends(verify_token)])
async def get_active_voice(object_id: str):
    """回显当前活跃克隆音色 uri(未设返 null=用预设)"""
    redis = await get_redis()
    uri = await redis.get(_K_ACTIVE.format(oid=object_id))
    return {"object_id": object_id, "uri": uri}


@router.put("/tts/voice/active", dependencies=[Depends(verify_token)])
async def set_active_voice(object_id: str, body: dict = Body(...)):
    """设/清当前活跃克隆音色。body {uri}:非空=用该克隆 uri(全 TTS 自动复用);空/缺=清除回退预设。"""
    uri = (body.get("uri") or "").strip() or None
    redis = await get_redis()
    key = _K_ACTIVE.format(oid=object_id)
    if uri:
        await redis.set(key, uri)
    else:
        await redis.delete(key)
    return {"object_id": object_id, "uri": uri}


# ================ GPT-SoVITS 就绪状态(M-tts-2,2026-08-10) ================
# 本地启动器(api_v2+frpc)就绪后定期上报心跳 → Redis 缓存;前端 status 查询心跳命中就不探测 frp。

@router.get("/tts/gptsovits/status", dependencies=[Depends(verify_token)])
async def gptsovits_status(force: bool = False, probe: bool = True):
    """GPT-SoVITS 就绪状态。心跳缓存优先(命中不打 frp);force=True 跳心跳强探;
    probe=False 只读心跳(前端折叠态/轮询用,绝不打 frp)。"""
    redis = await get_redis()
    return await check_gptsovits_status(redis, force=force, probe=probe)


@router.post("/tts/gptsovits/heartbeat", dependencies=[Depends(verify_token)])
async def gptsovits_heartbeat(body: dict = Body(...)):
    """本地启动器上报心跳。body {ready, gpt_model?, sovits_model?, latency_ms?}。
    ready=true 写 Redis TTL 90s(启动器每 30s 续期);ready=false 清除(启动器关闭时上报)。"""
    redis = await get_redis()
    ready = bool(body.get("ready", False))
    if ready:
        payload = {
            "ready": True,
            "ts": int(time.time()),
            "models": {
                "gpt_model": body.get("gpt_model", ""),
                "sovits_model": body.get("sovits_model", ""),
            },
            "latency_ms": body.get("latency_ms", -1),
            "reported_by": body.get("reported_by", "launcher"),
        }
        await redis.set(HEARTBEAT_KEY, json.dumps(payload), ex=HEARTBEAT_TTL)
        return {"ok": True, "ttl": HEARTBEAT_TTL}
    await redis.delete(HEARTBEAT_KEY)
    return {"ok": True, "cleared": True}
