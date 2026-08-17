"""
REST API 层(M3 起)
按域拆分 router:评分/反推(rest_score)、后续历史(rest_chat,M7)、心情(rest_mood,M7)等。
鉴权统一用 X-Access-Token(Header 或 query),依赖复用各 router 内的 _auth。

作者: 李文煜
日期: 2026-06-28
"""
