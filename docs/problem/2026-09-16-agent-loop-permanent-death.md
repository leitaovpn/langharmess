# 省略 api_key/base_url 的 /stream 请求永久杀死 agent loop

日期：2026-09-16
状态：已修复（`_rebuild` 捕获 provider 异常并降级 graph=None，loop 实例不再进入 ERRONEOUS；回归测试 + 真实服务复验通过）

## 现象

真实 CLI 端到端测试中，前 12 轮 /stream 全部正常；第 13 个请求（直接 API
客户端，只带 `model` 不带 `api_key`/`base_url`）返回
`503 {"detail": "Agent loop unavailable"}`，此后**所有请求**（包括带完整
凭据的）**永远 503**。重启服务或新建 agent（触发重新物化）才能恢复。

## 最小复现

纯 HTTP，无需本项目代码介入（`docs/problem/repro/repro_loop_death.py`）：

```text
S1: POST /stream {model, api_key, base_url, protocol: chat}  → 200 ✓
S2: POST /stream {model, protocol: chat}（无 key/url）        → 503 "Agent loop unavailable"
S3: POST /stream {model, api_key, base_url, protocol: chat}  → 仍 503（不恢复）
```

## 根因链

in-process 插桩拿到完整 traceback，链路如下：

1. `src/langharness_api/plugins/routes/stream.py:130-148`
   `_apply_agent_configuration` 只把非空的 `api_key`/`base_url` 写进
   properties → 合并后的 llm 描述符缺这两个属性。
2. `src/langharness_core/plugins/agents/directory.py:143-161`
   `ensure_plugin_instance` 发现描述符变化 → `_safe_kill` 杀掉**正在工作的**
   scoped llm 实例，重建一个配置残缺的新实例。
3. agent loop 的 `_llm_provider` 是 `@RequiresBest(..., optional=False)`
   必需依赖 → 重绑后 iPOPO 重新校验 → `@Validate` → `_rebuild()` →
   调 `llm.get_model()`。
4. `src/langharness_core/plugins/llm/llm.py:54-62`：model 有名字但
   key/url 为空 → 走 `init_chat_model(self._model_name)` 兜底 → 对非标准
   模型名抛 `ValueError: Unable to infer model provider`。
5. 异常穿透 `@Validate` 回调 → iPOPO 把实例置为 **ERRONEOUS
   （`StoredInstance.ERRONEOUS = 4`）**。iPOPO 对 ERRONEOUS 实例不会自动
   恢复（只有手动调 `retry_erroneous` 才会重试，本项目没有任何地方调用）
   → loop 服务永久注销，`find_service` 返回 None，路由持续 503。

## 触发面

- CLI 本身永远发送完整凭据，不会触发；触发面是直连 API 的客户端，包括
  「agent 已配置 llm、请求省略凭据」这种 API 契约允许的调用方式。
- 一次坏请求拖垮整个 agent 直至重启，是活性故障。

## 修复方向（三选一或组合）

1. loop 的 `_rebuild`/`@Validate` 必须捕获 provider 异常，绝不能让异常
   穿透 iPOPO 校验回调（ERRONEOUS 不可自愈）；
2. 路由层在杀实例**之前**校验合并后的 llm 配置，缺凭据直接 400；
3. `ensure_plugin_instance` 做成事务式：新实例创建并校验成功后再杀旧的，
   失败时回滚保留原实例。

## 修复记录（2026-09-16）

- `agent_loop.py` `_rebuild` 整体 try/except：provider 异常（如 `get_model()`
  对无凭据配置抛 ValueError）降级为 `graph=None` 并记日志，绝不让异常穿透
  iPOPO 校验/绑定回调（穿透即 ERRONEOUS 永久死亡）。
- 新增回归测试 `tests/test_agent_loop_resilience.py`（`_rebuild` 不抛异常 +
  目录级 rebind 到坏配置后 loop 服务存活、回绑好配置后 graph 恢复）。
- 真实服务复验：S1 带凭据 200 → S2 省略凭据 200（error 事件，仅该请求失败）
  → S3 带凭据 200（自愈），全程无 503；服务端日志记录
  "Agent graph rebuild failed; graph is unavailable"。
