"""
插件管理器 PluginManager
扫描插件目录、解析 manifest、按文件路径导入 entry、实例化、注册钩子(按对象门控)、
管理全局开关与按对象配置、支持 reload。

生命周期:discover → load → enable → (hook 调用) → disable → unload;reload = 先 unload 再 load。
配置存储:
  全局开关      mychat:plugin:{name}:enabled            = "0"/"1"
  按对象配置    mychat:plugin_cfg:{object_id}:{name}    = JSON({enabled, params})
解析规则(is_enabled_for):全局(总闸)关 → False;全局开 → 取按对象 enabled 位(未设置则 True)。

M2 阶段:plugin_dir 内无业务插件,discover 返回空,总线空载。

作者: 李文煜
日期: 2026-06-27

2026-06-27
变更说明：
  1. M2 从 V1.0 移植 PluginManager 到 V2.0(零业务改动)
"""
import importlib.util
import json
import logging
import sys
from pathlib import Path

from redis.asyncio import Redis

from core.config import settings
from plugins.manifest import parse_manifest, PluginManifest
from plugins.base import Plugin, PluginContext, HookResult
from plugins.event import EventBus

logger = logging.getLogger(__name__)


def _k_global_enabled(name: str) -> str:
    """全局开关 Redis 键"""
    return f"mychat:plugin:{name}:enabled"


def _k_obj_cfg(object_id: str, name: str) -> str:
    """按对象配置 Redis 键"""
    return f"mychat:plugin_cfg:{object_id}:{name}"


class PluginManager:
    def __init__(self, redis: Redis, bus: EventBus, plugin_dir: Path):
        self._redis = redis
        self._bus = bus
        self._dir = plugin_dir
        # name -> {"manifest", "plugin", "module"}
        self._loaded: dict[str, dict] = {}

    # —— 发现 ——
    def discover(self) -> list[PluginManifest]:
        """扫描插件目录,返回所有合法插件的 manifest。
        跳过:非目录、_ 前缀目录(如 _template)、. 前缀目录、无 plugin.yaml 的目录。"""
        out: list[PluginManifest] = []
        if not self._dir.is_dir():
            return out
        for sub in sorted(self._dir.iterdir()):
            if not sub.is_dir() or sub.name.startswith("_") or sub.name.startswith("."):
                continue
            yml = sub / "plugin.yaml"
            if not yml.is_file():
                continue
            try:
                out.append(parse_manifest(yml))
            except Exception:
                logger.exception("skip invalid manifest: %s", yml)
        return out

    # —— 加载 ——
    async def load_all(self) -> list[str]:
        """发现并加载全部插件,注册到总线;单插件失败仅记录不影响其他。返回已加载名列表"""
        loaded: list[str] = []
        for mf in self.discover():
            try:
                await self.load(mf)
                loaded.append(mf.name)
            except Exception:
                logger.exception("load plugin failed: %s", mf.name)
        return loaded

    async def load(self, mf: PluginManifest) -> Plugin:
        """加载单个插件:导入 entry 模块 → 找 Plugin 子类 → 实例化 → on_load → 注册钩子。
        幂等:同名已加载则先 unload 旧实例。
        失败回滚:摘订阅/调 on_unload/清 sys.modules,避免半加载状态泄漏,再向上抛。"""
        if mf.name in self._loaded:
            await self.unload(mf.name)
        entry_path = self._dir / mf.name / mf.entry
        mod_name = f"_mychat_plugin_{mf.name}"
        instance: Plugin | None = None
        module = None
        try:
            module = self._import_entry(mf.name, entry_path)   # 已把模块写入 sys.modules
            plugin_cls = self._find_plugin_subclass(module)
            if plugin_cls is None:
                raise ValueError(f"插件 {mf.name} 的 {mf.entry} 未定义 Plugin 子类")
            instance = plugin_cls()
            instance.manifest = mf
            instance.pctx = PluginContext(manager=self, redis=self._redis, settings=settings, manifest=mf)
            await instance.on_load()
            instance._alive = True                              # 标记存活,gate 据此跳过已卸载实例
            self._register_hooks(instance)
            self._loaded[mf.name] = {"manifest": mf, "plugin": instance, "module": module}
            logger.info("plugin loaded: %s (hooks=%s)", mf.name, mf.hook_names)
            return instance
        except Exception:
            # 回滚已建立的副作用:摘订阅 → 尝试 on_unload → 清 sys.modules,避免半加载泄漏
            self._bus.unsubscribe_plugin(mf.name)
            if instance is not None and getattr(instance, "pctx", None) is not None:
                try:
                    await instance.on_unload()
                except Exception:
                    logger.exception("rollback on_unload failed: %s", mf.name)
            if module is not None:
                sys.modules.pop(mod_name, None)
            raise

    def _import_entry(self, name: str, entry_path: Path):
        """按文件路径导入插件入口模块(不污染 sys.path);模块名唯一化避免冲突。
        注册进 sys.modules 以便插件内 importlib 相对查找能命中。"""
        if not entry_path.is_file():
            raise FileNotFoundError(f"插件入口不存在: {entry_path}")
        mod_name = f"_mychat_plugin_{name}"
        spec = importlib.util.spec_from_file_location(mod_name, str(entry_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"无法为插件入口建立 spec: {entry_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        return module

    def _find_plugin_subclass(self, module):
        """在入口模块中找出 Plugin 的子类(排除直接导入的基类本身)。
        用 __module__ 匹配确保只选"在本模块定义"的类。"""
        for attr in dir(module):
            obj = getattr(module, attr, None)
            if (isinstance(obj, type) and issubclass(obj, Plugin)
                    and obj is not Plugin and obj.__module__ == module.__name__):
                return obj
        return None

    def _register_hooks(self, plugin: Plugin) -> None:
        """把 manifest 声明的钩子注册到总线;每个钩子包一层按对象门控回调"""
        mf = plugin.manifest
        for entry in mf.hooks:
            method = getattr(plugin, entry.name, None)
            if method is None:
                logger.warning("插件 %s 声明了钩子 %s 但未实现,跳过", mf.name, entry.name)
                continue
            self._bus.subscribe(entry.name, mf.name, entry.priority,
                                self._make_gate(plugin, mf.name, method))

    def _make_gate(self, plugin: Plugin, name: str, method):
        """生成门控回调:实例仍存活(_alive) 且 该对象启用此插件 才调用真方法。
        _alive 校验防止 unload/reload 期间对已卸载实例的脏执行(TOCTOU)。"""
        manager = self

        async def gate(ctx):
            if not getattr(plugin, "_alive", False):
                return HookResult.CONTINUE
            if not await manager.is_enabled_for(name, ctx.object_id):
                return HookResult.CONTINUE
            return await method(ctx)

        return gate

    # —— 卸载 ——
    async def unload(self, name: str) -> bool:
        """卸载插件:摘订阅 → 标记不存活 → on_unload(此时仍在 _loaded,可读自身配置) → 移除登记 → 清模块。
        顺序保证:on_unload 内可经 manager 读自身配置;_alive=False 让在途回调下一 await 边界跳过。"""
        info = self._loaded.get(name)
        if info is None:
            return False
        plugin = info["plugin"]
        self._bus.unsubscribe_plugin(name)      # 先摘订阅,避免 on_unload 期间被新 fire 误触
        plugin._alive = False                    # 在途回调在下一 await 边界看到即跳过(TOCTOU 缓解)
        try:
            await plugin.on_unload()             # _loaded 尚未移除,on_unload 内可读自身配置
        except Exception:
            logger.exception("plugin %s on_unload raised", name)
        self._loaded.pop(name, None)             # on_unload 完成后再移除登记
        sys.modules.pop(f"_mychat_plugin_{name}", None)
        return True

    async def unload_all(self) -> None:
        for name in list(self._loaded.keys()):
            await self.unload(name)

    # —— reload ——
    async def reload(self, name: str) -> Plugin:
        """热重载:重新解析 manifest 并 load(load 内部先 unload 旧实例)"""
        if name not in self._loaded:
            raise KeyError(f"插件未加载: {name}")
        mf = parse_manifest(self._dir / name / "plugin.yaml")
        return await self.load(mf)

    # —— 全局开关 ——
    async def set_global_enabled(self, name: str, enabled: bool) -> None:
        await self._redis.set(_k_global_enabled(name), "1" if enabled else "0")

    async def get_global_enabled(self, name: str) -> bool:
        """全局开关;Redis 未显式设置时回退 manifest.default_enabled"""
        v = await self._redis.get(_k_global_enabled(name))
        if v is None:
            info = self._loaded.get(name)
            return info["manifest"].default_enabled if info else False
        return v == "1"

    # —— 按对象配置 ——
    async def get_object_config(self, name: str, object_id: str) -> dict:
        """取按对象配置 JSON;不存在/损坏返回 {}"""
        raw = await self._redis.get(_k_obj_cfg(object_id, name))
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    async def set_object_config(self, name: str, object_id: str,
                                enabled: bool | None, params: dict | None) -> None:
        """写入按对象配置(合并写整条 JSON);enabled/params 为 None 表示不改该项。
        params 必须为 dict(违例抛 ValueError,由 REST 层转 400),避免损坏 get_params。"""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params 必须是字典")
        cfg = await self.get_object_config(name, object_id)
        if enabled is not None:
            cfg["enabled"] = bool(enabled)
        if params is not None:
            cfg["params"] = params
        await self._redis.set(_k_obj_cfg(object_id, name), json.dumps(cfg, ensure_ascii=False))

    async def is_enabled_for(self, name: str, object_id: str) -> bool:
        """解析某对象是否启用此插件:全局(总闸)关 → False;
        全局开 → 取按对象 enabled 位(未显式设置则 True,即全局开默认对该对象启用)"""
        if not await self.get_global_enabled(name):
            return False
        obj_cfg = await self.get_object_config(name, object_id)
        if "enabled" in obj_cfg:
            return bool(obj_cfg["enabled"])
        return True

    async def get_params(self, name: str, object_id: str) -> dict:
        """取某对象此插件的参数:config_schema 默认值 ← 按对象 params 覆盖"""
        defaults: dict = {}
        info = self._loaded.get(name)
        if info:
            for k, spec in (info["manifest"].config_schema or {}).items():
                if isinstance(spec, dict) and "default" in spec:
                    defaults[k] = spec["default"]
        obj_cfg = await self.get_object_config(name, object_id)
        params = dict(defaults)
        raw_params = obj_cfg.get("params") or {}
        if isinstance(raw_params, dict):     # 防御:历史脏数据非 dict 时不致 get_params 抛错
            params.update(raw_params)
        return params

    # —— 查询 ——
    def list_loaded(self) -> list[str]:
        return sorted(self._loaded.keys())

    def get_manifest(self, name: str):
        info = self._loaded.get(name)
        return info["manifest"] if info else None

    def get_instance(self, name: str):
        info = self._loaded.get(name)
        return info["plugin"] if info else None

    @staticmethod
    def manifest_to_dict(mf: PluginManifest) -> dict:
        """manifest 序列化为可返回前端的 dict。
        display_name 空回退 name,category 空规范化为 DEFAULT_CATEGORY(后端单一真源,前端无需再处理空值)。"""
        from plugins.manifest import DEFAULT_CATEGORY
        return {
            "name": mf.name,
            "display_name": mf.display_name or mf.name,
            "category": mf.category or DEFAULT_CATEGORY,
            "version": mf.version,
            "author": mf.author,
            "description": mf.description,
            "hooks": [{"name": h.name, "priority": h.priority} for h in mf.hooks],
            "default_enabled": mf.default_enabled,
            "config_schema": mf.config_schema,
            "requires": mf.requires,
        }
