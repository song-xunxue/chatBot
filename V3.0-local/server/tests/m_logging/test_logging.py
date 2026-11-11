"""
应用日志配置单测(2026-08-04,logging 盲区修复)
钉死 setup_logging 行为:根 handler 挂载 / 级别生效 / 非法值兜底 / env 覆盖 / 幂等不重复 /
uvicorn 整合(propagate=False)/ 第三方噪音压制 / 业务 INFO 可达 root handler(盲区核心)。
2026-11-10 增强落盘:滚动文件(server.log)+ ERROR 归档(error.log 只收 ERROR+)/ trace id 注入。

注意:setup_logging 用 dictConfig 会重置 root handlers,会冲掉 pytest caplog 的捕获 handler,
故可见性测试用自挂的 _CaptureHandler(在 setup_logging 之后加,不被 dictConfig 清),不用 caplog。
文件类测试用 tmp_path 隔离,结束前显式 close RotatingFileHandler(Windows 句柄不释放会挡 tmp 清理)。

日期: 2026-08-04

2026-11-10
变更说明：
  1. 新增落盘/归档/trace id 测试 5 条(滚动 handler 挂载/ERROR 闸门行为/关闭落盘/trace 流转/配置项)
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from core.config import Settings
from core.logging_config import setup_logging, set_trace_id, get_trace_id


class _CaptureHandler(logging.Handler):
    """捕获日志记录到列表(测试用,在 setup_logging 之后挂到 root)"""
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


@pytest.fixture
def restore_root_logger():
    """快照/还原根 logger 状态(setup_logging 是全局副作用,避免污染其他测试)"""
    handlers = logging.root.handlers[:]
    level = logging.root.level
    yield
    logging.root.handlers = handlers
    logging.root.setLevel(level)


def test_setup_logging_attaches_stream_handler(restore_root_logger):
    """setup_logging 后根 logger 必须挂 StreamHandler(业务日志才能输出到 stdout → docker logs)"""
    setup_logging("INFO")
    assert any(isinstance(h, logging.StreamHandler) for h in logging.root.handlers)


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_setup_logging_sets_root_level(level, restore_root_logger):
    """根 logger 级别随入参生效(INFO 默认 / DEBUG 排障 / WARNING 只看告警 / ERROR)"""
    setup_logging(level)
    assert logging.getLogger().level == getattr(logging, level)


def test_setup_logging_invalid_level_falls_back_info(restore_root_logger):
    """非法级别值兜底 INFO(不崩溃,保证启动不被坏配置阻断)"""
    setup_logging("BOGUS")
    assert logging.getLogger().level == logging.INFO
    setup_logging("")
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_idempotent(restore_root_logger):
    """重复调用不累积 handler(dictConfig 重置而非追加;热配置/测试可安全多次调)"""
    setup_logging("INFO")
    n1 = len(logging.root.handlers)
    setup_logging("INFO")
    setup_logging("DEBUG")
    assert len(logging.root.handlers) == n1


def test_uvicorn_loggers_integrated(restore_root_logger):
    """uvicorn 三件套走同一 handler 且 propagate=False(避免与 root 重复输出,与业务日志同格式)"""
    setup_logging("INFO")
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        assert lg.propagate is False
        assert any(isinstance(h, logging.StreamHandler) for h in lg.handlers)


def test_third_party_noise_suppressed(restore_root_logger):
    """第三方库(httpx/httpcore/asyncio)压到 WARNING,避免 DEBUG 连接细节刷屏"""
    setup_logging("INFO")
    for name in ("httpx", "httpcore", "asyncio"):
        assert logging.getLogger(name).level == logging.WARNING


def test_business_logger_info_reaches_root_handler(restore_root_logger):
    """盲区核心:业务 logger.info 在 INFO 级可达 root handler(修复前被默认 lastResort 丢弃)"""
    setup_logging("INFO")
    cap = _CaptureHandler()
    root = logging.getLogger()
    root.addHandler(cap)  # setup_logging 之后挂,不被 dictConfig 清
    try:
        logging.getLogger("app.memory.coordinator").info("学到用户称呼 oid=test alias=主人")
    finally:
        root.removeHandler(cap)
    assert any("学到用户称呼" in m for m in cap.records)


def test_business_logger_level_follows_root(restore_root_logger):
    """业务 logger 未单独设级别时有效级别跟随 root(级别闸门由 root 把)"""
    biz = logging.getLogger("app.memory.coordinator")
    setup_logging("WARNING")
    assert biz.getEffectiveLevel() == logging.WARNING
    setup_logging("DEBUG")
    assert biz.getEffectiveLevel() == logging.DEBUG


def test_log_level_from_env(monkeypatch):
    """settings.log_level 读 env 的 LOG_LEVEL(pydantic env 优先于 .env;排障改 env 免改代码)"""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.log_level.upper() == "DEBUG"


def test_log_level_is_valid_level():
    """log_level 字段存在且为合法级别(默认 INFO;本地 .env 可能覆盖但不影响合法性)"""
    s = Settings()
    assert s.log_level
    assert s.log_level.upper() in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


# —— 2026-11-10 增强落盘 + trace id ——
def _close_file_handlers():
    """收尾:close 并摘掉 dictConfig 建的文件句柄(Windows 下不关会挡 tmp_path 清理)"""
    for h in list(logging.root.handlers):
        if isinstance(h, RotatingFileHandler):
            h.close()
            logging.getLogger().removeHandler(h)


def test_setup_logging_attaches_rotating_file_handlers(restore_root_logger, tmp_path):
    """落盘:root 挂 RotatingFileHandler×2(server.log 全量 + error.log 只收 ERROR+)"""
    setup_logging("INFO", log_dir=str(tmp_path))
    files = [h for h in logging.root.handlers if isinstance(h, RotatingFileHandler)]
    assert len(files) == 2
    # server.log 不设 handler 级别 = NOTSET(0) 全收(闸门在 root);error.log 独立闸门 ERROR
    assert sorted(h.level for h in files) == [0, logging.ERROR]
    assert {Path(h.baseFilename).name for h in files} == {"server.log", "error.log"}
    # uvicorn 三件套同步带上文件 handler(与业务日志同落盘)
    assert any(isinstance(h, RotatingFileHandler) for h in logging.getLogger("uvicorn").handlers)
    _close_file_handlers()


def test_error_archive_only_receives_error(restore_root_logger, tmp_path):
    """ERROR 归档行为:WARNING 不入 error.log;ERROR+ 两边都收(server.log 全量/error.log 归档)"""
    setup_logging("INFO", log_dir=str(tmp_path))
    lg = logging.getLogger("biz.test.archive")
    lg.warning("这条警告不该进归档")
    lg.error("这条错误该进归档")
    _close_file_handlers()
    err_text = (Path(tmp_path) / "error.log").read_text(encoding="utf-8")
    full_text = (Path(tmp_path) / "server.log").read_text(encoding="utf-8")
    assert "这条警告" not in err_text
    assert "这条错误" in err_text
    assert "这条警告" in full_text and "这条错误" in full_text


def test_file_disabled_keeps_console_only(restore_root_logger):
    """log_file_enable=False 仅 console(不落盘;测试等纯内存场景用)"""
    setup_logging("INFO", log_file_enable=False)
    assert not any(isinstance(h, RotatingFileHandler) for h in logging.root.handlers)
    assert any(isinstance(h, logging.StreamHandler) for h in logging.root.handlers)


def test_trace_id_flows_into_format(restore_root_logger, tmp_path):
    """trace id:set_trace_id 注入格式 %(trace_id)s;复位回 '-'(每请求隔离)"""
    setup_logging("INFO", log_dir=str(tmp_path))
    assert get_trace_id() == "-"   # 默认占位
    set_trace_id("deadbeef")
    logging.getLogger("biz.test.trace").warning("带 trace 的日志")
    set_trace_id("")   # 中间件 finally 复位
    logging.getLogger("biz.test.trace").warning("复位后的日志")
    _close_file_handlers()
    text = (Path(tmp_path) / "server.log").read_text(encoding="utf-8")
    assert "[deadbeef] biz.test.trace" in text   # 注入生效
    assert "[-] biz.test.trace" in text          # 复位生效


def test_log_settings_fields_exist():
    """落盘配置项存在且默认合理(log_dir 空=栈根 logs/;10MB×5)"""
    s = Settings()
    assert s.log_dir == ""
    assert s.log_file_max_bytes >= 1024
    assert s.log_file_backups >= 0
