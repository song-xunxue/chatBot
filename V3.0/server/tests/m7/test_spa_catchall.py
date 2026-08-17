"""
main.py SPA catch-all 单测(修子路由刷新 404):
1. main.py 实际 catch-all(GET /history 等前端路由返 index.html 200,非 404;API /health 优先)—— 需 dist 已构建
2. catch-all 模式隔离单测(无 dist 依赖):前端路由→index.html / 静态文件→透传

作者: 李文煜
日期: 2026-07-05
"""
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from core.config import PROJECT_ROOT

_dist = PROJECT_ROOT / "dashboard" / "dist"


@pytest.mark.skipif(not (_dist / "index.html").is_file(), reason="需 dashboard/dist/index.html 已构建")
async def test_main_spa_catch_all_no_404_on_refresh():
    """main.py 实际 catch-all:刷新前端子路由(/history /persona 等)返 index.html(200),非 404;
    /health(API)优先匹配不被吞。ASGITransport 不走 lifespan,无需 redis/QQ。"""
    import main
    app = main.app   # 模块级 create_app() 已构建(catch-all 在 dist 存在时注册)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        for path in ("/history", "/persona", "/memory", "/plugin", "/system"):
            r = await ac.get(path)
            assert r.status_code == 200, f"{path} 应返 index.html,实际 {r.status_code}"
            assert "text/html" in r.headers["content-type"]
        # API 路由优先匹配,不被 catch-all 吞
        assert (await ac.get("/health")).json()["status"] == "ok"


async def test_spa_catch_all_pattern_isolates_static_vs_route(tmp_path):
    """catch-all 模式单测(无 dist 依赖):前端路由→index.html / 真实静态文件→透传"""
    (tmp_path / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    app = FastAPI()
    dist_resolved = tmp_path.resolve()

    @app.get("/{full_path:path}")
    async def spa_serve(full_path: str):
        target = (tmp_path / full_path).resolve()
        try:
            target.relative_to(dist_resolved)
        except ValueError:
            raise HTTPException(status_code=404)
        if full_path and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(tmp_path / "index.html"))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as ac:
        assert "SPA" in (await ac.get("/history")).text      # 前端路由 → index.html
        assert (await ac.get("/")).status_code == 200         # 根 → index.html
        assert "console.log" in (await ac.get("/assets/app.js")).text   # 静态文件透传
