"""
NapCat WebUI 观看代理(2026-11-03):绕过 NapCat 4.x 对 QQNT 自动登录的状态机误报。

背景:两栈 QQ 均为自动快速登录,NapCat WebUI 后端状态机不认这种形态
(CheckLoginStatus 返回 isLogin=false/loginPhase=waiting_qrcode,QQ 本体实际在线收发正常),
前端「未登录即强制跳 QQ 登录页」把用户钉死在登录页,而该页又报「已登录无法重复登录」死路。

本代理 = 纯"观看滤镜":只改写两个响应让前端放行,其余请求(含鉴权/配置/日志 API)原样透传
NapCat 本体(6099/6089);QQ 与 NapCat 进程零改动,不动登录态,零风险。

改写规则:
  POST /api/QQLogin/CheckLoginStatus → data.isLogin=true(前端不再强制跳转)
  POST /api/QQLogin/GetQQLoginInfo   → data 填 uin/nick(主页信息卡不空白)

用法(两个端口各起一个实例,或只起要看的那个):
  python scripts/napcat_webui_proxy.py --target 6099 --listen 7099 --uin 1145077465 --nick 浅笑安然
  python scripts/napcat_webui_proxy.py --target 6089 --listen 7089 --uin 3682822273 --nick 浔与昳的大肥鱼
浏览器访问 http://127.0.0.1:<listen>/webui ,WebUI 密码与原端口相同。

日期: 2026-11-03
"""
import argparse
import json

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response

app = FastAPI(docs_url=None, redoc_url=None)
ARGS = argparse.Namespace(target=6099, uin='', nick='')
client = httpx.AsyncClient(timeout=30)

# 透传时剥离的逐跳头(代理自己重新组织)
# accept-encoding 必须剥:浏览器声明 br/zstd 而 httpx 不一定带解码包,服务器返回的压缩体
# 解不开会原样透传——浏览器拿到"压缩字节被当明文"即全页乱码(2026-11-03 实测修复)
_HOP = {'host', 'content-length', 'connection', 'transfer-encoding',
        'content-encoding', 'keep-alive', 'accept-encoding'}


@app.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD'])
async def proxy(request: Request, path: str):
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    try:
        r = await client.request(request.method, f'http://127.0.0.1:{ARGS.target}/{path}',
                                 content=body, headers=headers,
                                 params=dict(request.query_params))
    except Exception as e:
        return Response(f'proxy upstream error: {e}', status_code=502)

    content = r.content
    ctype = r.headers.get('content-type', '')
    if path.startswith('api/QQLogin/CheckLoginStatus'):
        try:
            d = r.json()
            data = d.get('data') or {}
            data['isLogin'] = True                      # 前端放行(实际登录态不受影响)
            if data.get('loginPhase') in ('offline', 'waiting_qrcode', None):
                data['loginPhase'] = 'ready'
            d['data'] = data
            content = json.dumps(d, ensure_ascii=False).encode()
        except (json.JSONDecodeError, ValueError):
            pass
    elif path.startswith('api/QQLogin/GetQQLoginInfo'):
        try:
            d = r.json()
            data = d.get('data') or {}
            if not data.get('uin'):
                data.update({'uin': ARGS.uin, 'nick': ARGS.nick, 'uid': ARGS.uin})
            d['data'] = data
            content = json.dumps(d, ensure_ascii=False).encode()
        except (json.JSONDecodeError, ValueError):
            pass

    out_headers = {k: v for k, v in r.headers.items() if k.lower() not in _HOP}
    return Response(content=content, status_code=r.status_code,
                    headers=out_headers, media_type=ctype or None)


def main() -> None:
    ap = argparse.ArgumentParser(description='NapCat WebUI 观看代理(状态机误报绕行)')
    ap.add_argument('--target', type=int, required=True, help='上游 NapCat WebUI 端口(6099/6089)')
    ap.add_argument('--listen', type=int, required=True, help='本代理监听端口(建议 7099/7089)')
    ap.add_argument('--uin', default='', help='主页信息卡展示的 QQ 号')
    ap.add_argument('--nick', default='', help='主页信息卡展示的昵称')
    a = ap.parse_args()
    ARGS.target, ARGS.uin, ARGS.nick = a.target, a.uin, a.nick
    uvicorn.run(app, host='127.0.0.1', port=a.listen, log_level='warning')


if __name__ == '__main__':
    main()
