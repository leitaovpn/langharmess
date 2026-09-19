# LangHarmess 四模块启动架构方案（init / ui / server / agent）

## Summary

采用“进程内微内核 + iPOPO 服务总线 + Python entry points”的架构，新增一个 `langharness` 启动编排包。现有包保持不重命名，职责映射为：

- `langharness`：新增的 init/启动模块
- `langharness_cli`：ui 模块，继续使用当前终端交互 UI
- `langharness_api`：server 模块，REST API、鉴权、限流、token 统计
- `langharness_core`：agent 模块，管理多个 agent loop

统一入口：

```bash
langharness --mode ui|all|server \
  --server-ip 127.0.0.1 \
  --server-port 11534 \
  --config-dir ~/.langharness
```

默认 `--mode all`、默认 `server-ip=127.0.0.1`、默认 `server-port=11534`。同时支持 `--config_dir` 作为兼容别名。

---

## Key Changes

### 1. 新增 `langharness` 启动模块

- 新建 `src/langharness/__main__.py` 作为统一入口。
- 控制台脚本改为：

```toml
[project.scripts]
langharness = "langharness.__main__:main"
```

- 旧的 `langharness_cli.__main__:main` 保留为兼容入口，但内部委托给新 bootstrap。
- 打包脚本的 PyInstaller 入口和 `--collect-submodules` 增加 `langharness`，并指向 `src/langharness/__main__.py`。

### 2. 先加载 config entry point

新增独立配置入口组：

```toml
[project.entry-points."langharness.config"]
config = "langharness_config.plugin:builtin_package"
```

启动流程：

1. 解析全局参数 `--mode`、`--server-ip`、`--server-port`、`--config-dir`。
2. 读取 `entry_points(group="langharness.config")`。
3. `EntryPoint.load()` 得到 `builtin_package`，调用后获得 `PluginPackage`。
4. 用最小 `PluginManager` 安装 config 插件，获取 `SPEC_CONFIGS` 服务。
5. 读取 `{config-dir}/langharness.toml`。
6. 根据 mode 组装 ui/server/agent/log 插件。

### 3. `langharness.toml` 增加模块选择配置

```toml
[plugins.ui]
builtin_package = "langharness_cli.plugin:builtin_package"
sdk_package = "langharness_api.sdk:package"

[plugins.server]
builtin_package = "langharness_api.plugin:builtin_package"

[plugins.agent]
builtin_package = "langharness_core.plugin:builtin_package"

[plugins.log]
builtin_package = "langharness_logging.plugin:builtin_package"
```

所有 `builtin_package`、`sdk_package` 都按 `module:attr` 形式加载，用统一的 `importlib` loader：

- `load("langharness_api.plugin:builtin_package")`
- 调用返回对象，校验是否为 `PluginPackage`
- 校验失败时明确报告 `config-dir`、section 和 import 路径

当前内置包已有 `langharness_cli.plugin:builtin_package`、`langharness_api.plugin:builtin_package`、`langharness_core.plugin:builtin_package`、`langharness_logging.plugin:builtin_package`。需要新增 `langharness_api.sdk:package`，封装现有 httpx 客户端为 UI 可替换的 SDK 服务。

### 4. 进程模型与 mode 行为

- `--mode server`
  - 同一进程加载 config + server + agent + log
  - 启动 FastAPI server，绑定 `server-ip:server-port`
  - agent 模块和 server 模块在同一 `PluginManager` 内

- `--mode ui`
  - 只加载 config + ui + log
  - 通过 REST SDK 访问 server
  - 不拉起 server；目标 server 必须已在运行

- `--mode all`
  - UI 作为前台进程
  - 若目标 server 已存在则复用；否则拉起一个 server 子进程
  - 守护由 bootstrap 调用 `langharness.api_guard.APIGuard` 执行，base url、host、port、config-dir 由统一启动参数注入
  - 等效于“ui 模式 + server 守护”

- 连接地址统一由 `--server-ip`/`--server-port` 拼接（通配 bind 地址映射为 `127.0.0.1`）；CLI 子命令不再接受自己的 `--base-url`，base_url 由 bootstrap 注入 ui 模块。

- `--mode` 未指定时默认 `all`。

“启动多个 ui 时后台只启动 1 个 server”通过健康检查实现：先请求 `GET /health`，成功则复用，失败才启动 server 子进程。

### 5. 新增模块级服务契约

新增四个服务规格：

```python
SPEC_UI_SERVER = "ui.server"
SPEC_SERVER_SERVER = "server.server"
SPEC_AGENT_SERVER = "agent.server"
SPEC_UI_SDK = "ui.server_sdk"
```

最小接口：

- `UIServerProvider`
  - `run(config) -> int`

- `ServerServerProvider`
  - `set_agent(agent) -> None`
  - `server(host, port) -> None`

- `AgentServerProvider`
  - `list_agents()`
  - `get_loop(agent_id)`
  - `reload(agent_id | None)`
  - `replace_loop_package(package_id, contribution_id)`

- `UISdkProvider`
  - 封装 health、chat stream、session、plugin 配置等 REST 调用

### 6. server 与 agent 直接通信

`server` 模块通过 iPOPO 注入 `SPEC_AGENT_SERVER`，启动时显式执行：

```python
server.set_agent(agent)
```

或由 `ServerServerProvider` 使用 `RequiresBest` 自动注入。当前阶段采用同进程直接方法调用，不引入消息总线。

拆开 server/agent 的意义是：

- server 只负责 HTTP、鉴权、限流、token 统计
- agent 只负责 loop 生命周期和多 loop 编排
- 后续可整体替换 agent loop，而不改 server 路由

未来若迁移到消息总线，只替换 `set_agent` 和 `AgentServerProvider` 实现。

---

## 遇到的问题与成熟方案

### 当前实现的主要问题

1. 当前有 `langharness_cli` 和 `langharness_api` 两个入口，没有统一 `--mode`。
2. CLI 通过 `APIGuard` 隐式拉起 server，host/port 硬编码为 `8000`。
3. config 加载是硬编码 descriptor，不是先通过 entry point 发现 config 包。
4. ui/server/agent 的插件包是硬编码组装，无法从 `langharness.toml` 替换。
5. server 和 agent 没有 `set_agent` 边界，loop 替换耦合在 API 路由内部。
6. 缺少明确的“多 UI 共享一个 server”进程生命周期协议。

### 可参考的成熟方案

- `Pelix/iPOPO`：当前已经在用，是最成熟的 Python 服务组件容器，适合进程内模块化。
- Python 标准 `importlib.metadata.entry_points`：适合 config/plugin 声明式发现。
- `localstack/plux`：成熟的 entry-point 动态插件加载框架，可参考其包级 entry point 组织方式。
- `pytest` 的 `pluggy`：适合 hook 型插件系统，但本项目更适合服务契约型，不直接替换 iPOPO。
- `click-plugins`：适合 CLI 子命令插件，当前 CLI 已有类似机制。
- OSGi/Eclipse 生态：概念上与本项目一致，可作为长期演进参考，不直接用于 Python。

### 方案对比

- **方案 A：进程内微内核 + entry points（推荐）**
  - init 统一编排，server/agent 同进程，UI 通过 REST 访问 server。
  - 收益：清晰模块边界、支持动态替换、改动适中、契合现有 iPOPO。
  - 成本：需要新增 init 包、服务契约、配置加载和进程守护。

- **方案 B：server 与 agent 一开始就分进程 + 消息总线**
  - 使用 NATS、Redis Stream 或 ZeroMQ。
  - 收益：更强的隔离和横向扩展能力。
  - 成本：部署、序列化、故障恢复复杂度显著增加，当前阶段过早。

- **方案 C：不新增 init 包，只扩展当前 CLI/API flags**
  - 收益：改动最小。
  - 成本：模块边界仍然模糊，`--mode` 语义分散，后续动态替换 agent loop 困难。

最终选择 **方案 A**，保留未来向 **方案 B** 演进的可能性。

---

## Test Plan

### 单元测试

- config entry point 只加载 `langharness.config`，不混入 `langharness.plugins`。
- `langharness.toml` 缺少 `[plugins.*]` 时使用内置默认值并给出日志。
- `builtin_package` / `sdk_package` 的 `module:attr` 加载成功和失败路径。
- `--mode` 默认 `all`，非法 mode 报错。
- `--server-ip`、`--server-port`、`--config-dir` 的默认值和 `--config_dir` 别名。
- `server.set_agent(agent)` 注入关系。
- `APIGuard` 只在 `--mode all` 下被调用，`--mode ui` 不拉起 server。
- 多 UI 场景下，健康检查通过时不启动第二个 server。

### 集成 / e2e

- `langharness --mode server --server-port 11534` 启动后，`/health` 和 `/plugins/discovered` 正常。
- 已运行 server 时，启动两个 `langharness --mode ui`，验证只存在一个 server 进程。
- `langharness --mode all` 启动后，UI 能访问自动拉起的 server。
- 动态替换 agent loop：
  - 安装新 agent loop package
  - `agent_server.replace_loop_package(...)`
  - 新 loop 生效，旧 loop 被卸载
- `make check` 全量通过：Ruff、mypy、Pyright、import check、pytest 覆盖率不低于 95%。

---

## Assumptions

- ui 复用当前 `langharness_cli` 终端交互界面，不新增 Web UI。
- 不重命名现有 `langharness_cli`、`langharness_api`、`langharness_core`，只新增 `langharness` 编排包。
- config 和 ui/server/agent/log 的 `builtin_package`、`sdk_package` 均使用 Python import 路径。
- 当前阶段 server 与 agent 同进程直接调用，消息总线只作为后续演进，不在本期实现。
- 统一 CLI 默认 server port 改为 `11534`；旧 `python -m langharness_api` 和旧 `langharness_cli` 入口保留兼容。
