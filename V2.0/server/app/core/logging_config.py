"""
应用日志配置(dictConfig)

背景(2026-08-04 修盲区):
  业务代码已全面使用 logging.getLogger(__name__)(26 文件 / 134 处,print 零使用),
  但 main.py 原未配置根 logger → Python3 默认 lastResort 只输出 WARNING+ 到 stderr,
  致所有 INFO/DEBUG 业务日志被吞,docker logs 仅见 uvicorn 自配的 access log。

  本模块在应用启动最早期(main.py import 阶段)统一配置:
    - 根 StreamHandler → stdout(Docker 捕获 docker logs)
    - 统一格式:时间 级别 logger名: 消息
    - uvicorn / uvicorn.access / uvicorn.error 显式走同一 handler(propagate=False 避免重复),与业务日志同格式
    - 第三方库(httpx/httpcore/asyncio)压到 WARNING,避免 DEBUG/INFO 刷屏
    - 级别由 settings.log_level 控制(默认 INFO;.env 设 LOG_LEVEL=DEBUG 排障)

  Dockerfile 配套 ENV PYTHONUNBUFFERED=1,确保 stdout 不缓冲、日志实时可见。

作者: 李文煜
日期: 2026-08-04

2026-08-04
变更说明：
  1. 新建:setup_logging dictConfig,修应用 logging 盲区(业务 INFO 日志原被默认配置丢弃)
"""
import copy
import logging
import logging.config

# 日志统一格式:时间 级别(8字符左对齐) logger名: 消息
_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# dictConfig 基线(root 级别运行时由 setup_logging 的 level 参数覆盖)
_BASE_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,  # 不禁用已创建的模块 logger(否则 import 顺序敏感,业务 logger 失效)
    "formatters": {
        "default": {
            "format": _LOG_FORMAT,
            "datefmt": _DATE_FORMAT,
        },
    },
    "handlers": {
        # 单一 console handler → stdout(Docker stdout 捕获 docker logs)
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # schema 协议指向 sys.stdout
            "formatter": "default",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",  # 占位,setup_logging 用 level 参数覆盖
    },
    "loggers": {
        # uvicorn 三件套:走同一 handler+格式(propagate=False 避免与 root 重复输出),与业务日志统一
        "uvicorn": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # 第三方库噪音压到 WARNING(httpx DEBUG 连接细节刷屏,业务无需)
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
        "asyncio": {"level": "WARNING"},
    },
}

# 合法日志级别(setup_logging 入参校验用,非法值回退 INFO)
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def setup_logging(level: str = "INFO") -> None:
    """配置根 logger:业务日志 + uvicorn 统一走 stdout,级别由 level 控制。

    参数:
        level: 根 logger 级别(默认 INFO;DEBUG 排障、WARNING 只看告警)。非法值回退 INFO。

    幂等:可重复调用(测试/热配置);每次 deepcopy 基线再覆盖级别,不累积 handler。
    """
    lvl = (level or "INFO").upper()
    if lvl not in _VALID_LEVELS:
        lvl = "INFO"
    cfg = copy.deepcopy(_BASE_CONFIG)
    cfg["root"]["level"] = lvl
    # uvicorn 三件套同步级别(DEBUG 放行 access;WARNING 则一并静音)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        cfg["loggers"][name]["level"] = lvl
    logging.config.dictConfig(cfg)
