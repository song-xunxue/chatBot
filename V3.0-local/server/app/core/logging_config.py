"""
应用日志配置(dictConfig)

背景(2026-08-04 修盲区):
  业务代码已全面使用 logging.getLogger(__name__)(26 文件 / 134 处,print 零使用),
  但 main.py 原未配置根 logger → Python3 默认 lastResort 只输出 WARNING+ 到 stderr,
  致所有 INFO/DEBUG 业务日志被吞,docker logs 仅见 uvicorn 自配的 access log。

  本模块在应用启动最早期(main.py import 阶段)统一配置:
    - 根 StreamHandler → stdout(Docker 捕获 docker logs)
    - 统一格式:时间 级别 [trace_id] logger名: 消息
    - uvicorn / uvicorn.access / uvicorn.error 显式走同一 handler(propagate=False 避免重复),与业务日志同格式
    - 第三方库(httpx/httpcore/asyncio)压到 WARNING,避免 DEBUG/INFO 刷屏
    - 级别由 settings.log_level 控制(默认 INFO;.env 设 LOG_LEVEL=DEBUG 排障)

  Dockerfile 配套 ENV PYTHONUNBUFFERED=1,确保 stdout 不缓冲、日志实时可见。

2026-11-10 增强批次:
  - 落盘滚动:RotatingFileHandler → logs/server.log(默认 10MB×5 个备份)。
    原本地栈靠启动器重定向 stdout(server.out.<ts>.log),每重启增殖一个文件且永不轮转;
    落盘后由 logging 体系统一管大小,launcher 重定向文件仅作启动期兜底。
  - ERROR 归档:logs/error.log 只收 ERROR+(独立滚动),排障先看它,不必翻全量 INFO。
  - trace id:contextvar + Filter 注入 %(trace_id)s;main.py 的 HTTP 中间件每请求生成
    8 位 hex(响应头 X-Trace-Id 同步带回),一次排障链路的日志行按 id 串联。
    请求内 create_task 的后台任务继承创建时上下文,天然带同一 id。

日期: 2026-08-04

2026-08-04
变更说明：
  1. 新建:setup_logging dictConfig,修应用 logging 盲区(业务 INFO 日志原被默认配置丢弃)

2026-11-10
变更说明：
  1. 落盘增强:server.log 滚动(10MB×5)+ error.log ERROR 归档(独立滚动);目录
     settings.log_dir(空=栈根 logs/),大小/份数 settings.log_file_max_bytes/log_file_backups
  2. trace id:contextvar + TraceIdFilter + set_trace_id/get_trace_id,格式串加 [%(trace_id)s]
"""
import copy
import logging
import logging.config
import logging.handlers
from contextvars import ContextVar
from pathlib import Path

# 日志统一格式:时间 级别 [trace_id] logger名: 消息
_LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(trace_id)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# trace id 上下文(每 HTTP 请求一换;未在请求上下文里显示 "-")
_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")


def set_trace_id(tid: str) -> None:
    """设置当前上下文的 trace id(HTTP 中间件每请求调用;传空串复位为 "-")"""
    _trace_id.set(tid or "-")


def get_trace_id() -> str:
    """读当前 trace id(测试/中间件用)"""
    return _trace_id.get()


class TraceIdFilter(logging.Filter):
    """把 contextvar 里的 trace id 注入每条 record(格式串 %(trace_id)s 消费)"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id.get()
        return True


# dictConfig 基线(root 级别运行时由 setup_logging 的 level 参数覆盖;
# 文件 handler 由 setup_logging 动态填充路径后并入)
_BASE_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,  # 不禁用已创建的模块 logger(否则 import 顺序敏感,业务 logger 失效)
    "filters": {
        "trace_id": {"()": "core.logging_config.TraceIdFilter"},  # 工厂写法指向本模块过滤器
    },
    "formatters": {
        "default": {
            "format": _LOG_FORMAT,
            "datefmt": _DATE_FORMAT,
        },
    },
    "handlers": {
        # console handler → stdout(Docker stdout 捕获 docker logs;本地栈启动器重定向兜底)
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # schema 协议指向 sys.stdout
            "formatter": "default",
            "filters": ["trace_id"],
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


def _default_log_dir() -> str:
    """默认日志目录 = 栈根 logs/(本文件在 <栈>/server/app/core/ 下,parents[3] 即栈根)"""
    return str(Path(__file__).resolve().parents[3] / "logs")


def setup_logging(level: str = "INFO", *, log_dir: str = "",
                  log_file_enable: bool = True,
                  file_max_bytes: int = 10 * 1024 * 1024,
                  file_backups: int = 5) -> None:
    """配置根 logger:console(stdout)+ 滚动落盘(server.log)+ ERROR 归档(error.log)。

    参数:
        level: 根 logger 级别(默认 INFO;DEBUG 排障、WARNING 只看告警)。非法值回退 INFO。
        log_dir: 日志目录(空 = 栈根 logs/;.env LOG_DIR 可覆盖)。
        log_file_enable: 是否落盘(False 仅 stdout;测试可关)。
        file_max_bytes / file_backups: server.log 与 error.log 各自的滚动阈值与备份数。

    幂等:可重复调用(测试/热配置);每次 deepcopy 基线再覆盖,dictConfig 重置而非追加 handler。
    """
    lvl = (level or "INFO").upper()
    if lvl not in _VALID_LEVELS:
        lvl = "INFO"
    cfg = copy.deepcopy(_BASE_CONFIG)
    cfg["root"]["level"] = lvl
    # uvicorn 三件套同步级别(DEBUG 放行 access;WARNING 则一并静音)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        cfg["loggers"][name]["level"] = lvl

    # 落盘 handler:server.log 全量滚动 + error.log 只收 ERROR+(排障先看它)
    if log_file_enable:
        d = log_dir or _default_log_dir()
        Path(d).mkdir(parents=True, exist_ok=True)   # 目录不存在则建(RotatingFileHandler 不自建父目录)
        # RotatingFileHandler:按大小滚动,delay=True 首条日志才开文件(避免空跑也占句柄)
        cfg["handlers"]["server_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(Path(d) / "server.log"),
            "maxBytes": max(1024, int(file_max_bytes)),   # 下限 1KB,防误配 0 死循环滚动
            "backupCount": max(0, int(file_backups)),
            "encoding": "utf-8",
            "formatter": "default",
            "filters": ["trace_id"],
            "delay": True,
        }
        cfg["handlers"]["error_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(Path(d) / "error.log"),
            "maxBytes": max(1024, int(file_max_bytes)),
            "backupCount": max(0, int(file_backups)),
            "encoding": "utf-8",
            "formatter": "default",
            "filters": ["trace_id"],
            "level": "ERROR",   # 独立闸门:只收 ERROR+(handler 级别,root 级别不影响它收什么)
            "delay": True,
        }
        for h in ("console", "server_file", "error_file"):
            cfg["root"]["handlers"].append(h)
            cfg["loggers"]["uvicorn"]["handlers"].append(h)
            cfg["loggers"]["uvicorn.error"]["handlers"].append(h)
            cfg["loggers"]["uvicorn.access"]["handlers"].append(h)

    logging.config.dictConfig(cfg)
