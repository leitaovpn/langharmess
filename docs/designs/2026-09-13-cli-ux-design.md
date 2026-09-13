# Claude Code 风格 CLI 交互界面设计方案

## 目标

将交互式 CLI 的呈现层重做为 **Claude Code 式流式终端**:

- 正文流式 markdown 渲染(节流,避免逐 token 重建)
- 紧凑工具调用行:运行中 `⠋ name args摘要` → 完成 `✓ name (耗时 · 大小)`,与正文按序交错
- 底部状态栏:工作态(spinner/模型/本响应 token)在 Live 内,空闲态在 prompt_toolkit 动态 bottom_toolbar(模型/累计 token//help 提示)
- 界面文案插件属性可配置(`plugin.ui.locale`,en/zh),非 tty 下纯文本降级(只追加不重印)
- 全部延续全插件设计(iPOPO 组件 + PluginDescriptor),无新依赖(rich 15 + prompt_toolkit 3)

## 事件契约

核心事件流(`PluginAgentLoop.astream`,经 `/stream` NDJSON 透传)在原有三种事件之外新增:

```json
{"type": "usage", "input_tokens": 123, "output_tokens": 45, "total_tokens": 168}
```

- 每响应结束时**只发一次**,值为该响应内多次模型调用的累加和;无 usage 时完全不发(向后兼容)。
- 生产端:LLM 插件开启 `stream_usage`(`plugin.model.stream_usage` 属性,默认 true),每个模型调用的末块经 langgraph messages 流携带 `usage_metadata`;`astream` 只从 **messages 分支**提取(updates 分支的 chunk 拼接会重复求和),提取器为 `_extract_usage`(usage_metadata 优先,回退 `response_metadata.token_usage`,全零返回 None)。
- 逃生阀(三级):插件属性 / `/stream` 请求体可选 `stream_usage` 字段 / CLI env `LANG_HARMESS_STREAM_USAGE=false`。

## 渲染器协议扩展

`InteractiveRenderer` 新增两个方法(旧渲染器不实现也可用,runner 侧 hasattr 守卫):

```python
def set_model(self, name: str) -> None: ...   # 状态栏显示模型名
def get_status_text(self) -> str: ...         # 空闲态 bottom_toolbar 文案
```

## 渲染器状态机(`RichInteractiveRenderer`)

- `_segments: list[str | _ToolRun]` 有序 transcript(相邻文本合并),`_tool_runs: dict[tool_call_id, _ToolRun]`
- `_session_usage`(跨响应累加)/ `_response_usage`(start_response 重置)
- 节流:`THROTTLE_SECONDS = 0.125`,assistant 事件只追加文本,≥125ms 或工具事件/finish 强制刷新时才重建帧(`Live refresh_per_second=8`)
- 工具行(纯客户端派生):耗时 = tool_call/tool_output 到达时间差(`time.monotonic`),大小 = UTF-8 字节人性化(B/KB/MB),输出以 `error` 开头 → `✗ name (error)`
- 状态行:thinking → `⠋ thinking… · model`;tool → 第一个运行中工具;有 usage → 追加 `1.2k in / 356 out`
- tty(`console.is_terminal`)走 Live;非 tty:`print(delta, end="", markup=False)` 只追加 + ASCII `+`/`✓`/`✗` 工具行

## i18n

`src/langharmess_cli/i18n.py` 纯模块:`LOCALES = ("en", "zh")`、`STRINGS` 双表、`tr(locale, key, **fmt)`(未知 locale/key 回退 en)、`get_locale()` 读 env `LANG_HARMESS_LOCALE`。配置机制仍是插件属性:渲染器与 shell 插件各加 `@Property("_locale", "plugin.ui.locale", "en")`,`__main__` 解析 env + `--locale` 后写入描述符 properties 并传给 runner。

## 验收要点

- `pytest --cov-fail-under=95`(141 用例,96.15%)、ruff/mypy/pyright 全绿;`tests/test_e2e.py` 未改且通过
- 手动:tty 下流式渲染平滑、工具行状态转换、工具栏 token 累计;`LANG_HARMESS_LOCALE=zh` 全中文;管道输出纯文本且正文不重复;`LANG_HARMESS_STREAM_USAGE=false` 逃生阀生效
