# Agent 身份 / 用户会话模型 / 插件配置持久化 设计方案

日期：2026-09-15
状态：已评审定稿（两轮需求讨论）

## 背景

当前的 langharness 只有"一个随机 session_id"这一层身份：

- CLI 每次启动生成 `uuid4().hex`（`langharness_cli/common/interactive.py:60`），换模型强制轮换（`:213`），退出即丢失，无法续接历史会话；
- 请求体中没有 user_id / agent_id，服务端只有一个硬编码的 agent loop 实例（`langharness_core/plugin.py:16`）；
- 插件配置每次启动现算（硬编码 + env + CLI 参数），既不落盘，也没有历史与回滚；`PluginRegistry.save/load` 存在但生产从未调用；
- checkpointer 用相对路径 `langharness_checkpoints.sqlite3`，落在 server 进程 CWD 而不是 `--dir`。

本设计引入：agent 身份与独立插件集、user/agent/session 三层身份模型、服务端会话索引、插件配置的持久化与版本回滚。

## 需求评审结论（逐条）

| 需求 | 结论 | 设计要点 |
|------|------|----------|
| 1. agent 需要身份 id 和描述 | 采纳，并扩展为**每 agent 独立插件集** | agent 注册表（`agents.json`）+ 每 agent 一套插件实例 |
| 2. 请求带 user_id/agent_id/会话 id；会话间记忆隔离；user↔agent 多对多、user↔会话一对多 | 采纳 | 记忆键 `thread_id = f"{user_id}::{session_id}"`；会话属于 user 且**可跨 agent 共享**；多对多仅记录使用关系 |
| 3. CLI 未指定 user_id 默认 `local_user` | 采纳 | `--user-id` > `LANG_HARNESS_USER_ID` > `local_user` |
| 4. CLI 可查看 agent、指定 agent_id | 采纳，默认值调整为**该用户最近一次使用的 agent** | `GET /agents` + `/agents`、`/agent <id>`；回退 `simple_agent` |
| 5. CLI 可查看历史会话 id，默认最近一次 | 采纳，索引放**服务端** | `GET /sessions` + `sessions.sqlite3`；`/sessions`、`/new` |
| 6. cli、api、agent 三层插件配置持久化 + 历史回滚 | 采纳，成功效改为**运行时热应用** | 版本流快照 + append-only 回滚；`swap_policy` 决定热应用或 `restart_required` |

评审中识别并接受的取舍：

- `user_id` 是客户端自述，静态 bearer token 下不构成安全边界，v1 仅作命名空间；
- 会话跨 agent 共享 ⇒ 同一 thread 的历史可能包含另一 agent 的工具调用；约束所有 agent 共享同一 state_schema/context_schema；
- 保留请求级模型覆盖（`model/api_key/base_url`），但只作用于该 agent 自己的 LLM 实例，不再有全局 runtime-llm。

## 目标架构

### 身份与会话数据模型

```
user_id    : ^[A-Za-z0-9._-]{1,64}$，默认 local_user
agent_id   : 注册表条目 id，默认 = 该用户最近会话的 last_agent_id，否则 simple_agent
session_id : uuid4 hex，属于 user（1:N），可跨 agent 使用
thread_id  : f"{user_id}::{session_id}"      # LangGraph 记忆隔离键
```

### 存储布局（统一在 `<dir>`，默认 `~/.langharness`）

```
<dir>/
  langharness.toml                  # 已有：provider 配置
  agents.json                       # agent 注册表，种子 simple_agent
  sessions.sqlite3                  # 会话索引
  langharness_checkpoints.sqlite3   # 从 CWD 迁移到 <dir>
  plugin_config/                    # P3
    cli.json  api.json              # 全局 scope
    agents/<agent_id>.json          # 每 agent 插件绑定 + 覆盖
```

会话索引表：`sessions(user_id, session_id, created_at, last_used_at, turns, last_agent_id, agents_used)`，主键 `(user_id, session_id)`；`agents_used` 为 JSON 数组，是 user↔agent 多对多的落地。

### 插件配置版本流（P3）

append-only，每版全量快照：

```json
{"schema": 1, "scope": "api", "current": 3,
 "history": [
   {"seq": 1, "ts": "...", "action": "init", "actor": "system",
    "config": {"plugins": {"workspace-tools": {"enabled": true, "properties": {}}}}},
   {"seq": 3, "ts": "...", "action": "rollback", "actor": "cli", "target_seq": 1, "config": {}}
 ]}
```

回滚 = 追加一个指向旧快照的新版本（前向可审计，不删历史）。写入时剥离 `api_key`/`token`/`secret` 等密钥字段并告警。

### 每 agent 独立插件集（P2）

iPOPO 标准 `@Requires`/`@RequiresBest` 处理器读取组件属性 `requires.filters`（`{字段: LDAP filter}`），在 `instantiate()` 时按实例覆盖依赖过滤器；instantiate 属性会合并进 `context.properties` 并注册为服务属性（pelix 3.2.2，已实测）。

```
ipopo.instantiate("agent-loop-factory", f"agent-loop@{aid}", {
  "plugin.agent_id": aid,
  "requires.filters": {
    "_llm_provider": f"(plugin.agent_id={aid})",
    "_tool_providers": f"(plugin.agent_id={aid})",
    "_system_prompt_providers": f"(plugin.agent_id={aid})",
    "_middleware_providers": f"(plugin.agent_id={aid})",
    "_name_provider": f"(plugin.agent_id={aid})"
  }})
```

不加 filter 的字段保持全局：`_checkpointer_provider`、`_store_provider`、`_state_schema_provider`、`_context_schema_provider`、`_debug_provider`。

**陷阱**：非法 filter 会被静默忽略并回退成不过滤（`requires.py:85-88`），拼错即把全局插件绑进来。必须在实例化前自行校验 filter，且所有 id 统一 `^[A-Za-z0-9._-]{1,64}$` 校验，杜绝 LDAP 注入。

### 契约（只增不改）

已 pin 的 Protocol 不能加方法或加无默认值参数（`validation.py` 会以 `MISSING_METHOD`/`PARAM_NOT_ACCEPTED` 拒绝既有实现），新增能力一律走新 spec：

| spec | 协议 | 方法 |
|------|------|------|
| `session.index` | `SessionIndexProvider` | `touch` / `list_sessions` / `get_session` / `new_session` |
| `agent.registry` | `AgentRegistryProvider` | `list_agents` / `get_agent`（CRUD 随 P3 API 扩展） |
| `agent.directory` | `AgentDirectoryProvider` | `list_agents` / `get_loop` / `reload` |
| `plugin.scope`（framework 层） | `ScopedPluginRegistrar` | `instantiate_instance` / `kill_instance` / `find_service` |

`PluginDescriptor` 新增 `swap_policy: "hot" | "restart" = "restart"`；`from_dict` 用 `data.get` 兼容旧 JSON。

### API / CLI 面

- `POST /stream`（P1）：新增 `user_id`、`agent_id`；`session_id/model/api_key/base_url` 改可选（缺省 session 由服务端新建）；首行 NDJSON 事件 `{"type":"session","session_id":...,"agent_id":...}`；每次请求 touch 会话索引。解析 agent 与 LLM 覆盖在短锁内完成，**流式阶段不持锁**（graph 对象为快照）。
- `GET /agents`、`GET /sessions?user_id=&limit=`（P1）。
- `GET/PUT /plugins[/{scope}][/history|/rollback]`、`POST/PUT/DELETE /agents/{id}`（P3）。
- CLI 参数：`--user-id`、`--agent-id`、`--session-id`、`--new-session`；命令：`/agents`、`/agent <id>`、`/sessions`、`/new`、`/whoami`（P1），`/plugins ...`（P3）；移除 provider 切换时的 session 轮换。

## 分阶段实施

- **P0**：本设计文档。
- **P1 身份与会话地基**：id 校验（`core/common/ids.py`）、会话索引 sqlite 插件、agent 注册表、`GET /sessions`、`GET /agents`、`/stream` 身份字段与 session 事件、checkpointer 路径迁移到 `<dir>`、CLI 参数与命令；附 `requires.filters` 实例隔离 spike 测试。agent 行为暂与现状一致（共享插件实例）。
- **P2 每 agent 独立插件集**：`PluginManager` scoped 实例能力（`plugin.scope`）、`AgentDirectory`、per-agent loop 物化、`/stream` 经 directory 解析 loop 并做 agent 级 LLM 覆盖、流式阶段释放锁。
- **P3 配置持久化 + 回滚 + 热应用 + agent CRUD**：版本化配置存储、`swap_policy`、`/plugins` API 与 CLI 命令族、agent CRUD、`AgentDirectory.reload` 重新物化。

## 风险与限制

- `user_id` 自述，无真实鉴权；仅命名空间。
- 会话跨 agent 共享限制 state_schema/context_schema 全局唯一；跨 agent 历史中的工具引用只作历史，不保证语义连贯。
- 短锁方案下并发流共用一个 AsyncSqliteSaver 连接，需在 P2 验证并发 checkpoint 写入。
- 密钥不落盘 ⇒ 回滚恢复的配置不含 api_key/token，需请求侧重新提供。
- 热替换时进行中的流继续使用旧 graph（预期行为）。
