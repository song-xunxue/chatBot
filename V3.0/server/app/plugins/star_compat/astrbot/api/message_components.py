"""astrbot.api.message_components 兼容(最小子集):Plain/At/Image/Reply。
V2.0 私聊场景主要用 Plain;其余占位供插件 import 不报错。

作者: 李文煜
日期: 2026-06-28
"""


class Plain:
    def __init__(self, text: str = ""):
        self.text = text


class At:
    def __init__(self, qq: str = "", name: str = ""):
        self.qq = qq
        self.name = name


class Image:
    def __init__(self, url: str = "", file: str = ""):
        self.url = url
        self.file = file


class Reply:
    def __init__(self, sender_nickname: str = "", message_str: str = "", chain=None):
        self.sender_nickname = sender_nickname
        self.message_str = message_str
        self.chain = chain or []
