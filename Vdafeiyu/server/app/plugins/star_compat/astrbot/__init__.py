"""astrbot 兼容包顶层(V2.0 子集)
模拟 AstrBot 顶层 import 路径,供 .star 插件 `from astrbot.api import star` 命中本兼容包。
StarLoader 启动时把 plugins/star_compat/ 加入 sys.path,使 `import astrbot` 解析到本目录。"""
import logging

logger = logging.getLogger("astrbot")
