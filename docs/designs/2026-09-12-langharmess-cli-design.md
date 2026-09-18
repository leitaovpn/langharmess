# langharness_cli 插件化 CLI 设计方案

## 目标

在 `src/langharness_cli` 中实现插件驱动的命令行工具：

- 通过 CLI 调用 `langharness_api` 提供的 API server
- 命令行子命令由插件动态加载
- CLI 执行前自动检测 API server 监听端口
- 若 API server 未启动，则自动拉起
- 设计先评审，批准后再开发

## 包结构

```text
src/langharness_cli/
├── __init__.py
├── contracts.py
├── runner.py
├── api_guard.py
└── plugins/
    ├── __init__.py
    └── commands/
        └── template_health.py
```

## 服务规范

```python
SPEC_CLI_COMMAND = "cli.plugin.command"
SPEC_CLI_RUNNER = "cli.runner"
```

## 插件契约

```python
@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    handler: Callable[[argparse.Namespace], int]


class CLICommandProvider(Protocol):
    def get_commands(self) -> list[CommandSpec]: ...
    def get_plugin_info(self) -> dict[str, str]: ...
```

## CLI Runner

`CLIRunner` 负责：

1. 启动 `PluginManager`
2. 加载所有 `cli.plugin.command` 服务
3. 创建 `argparse.ArgumentParser`
4. 遍历 command provider，注册子命令
5. 执行用户选择的子命令

```python
@ComponentFactory("cli-runner-factory")
@Provides(SPEC_CLI_RUNNER)
@Requires("_command_providers", SPEC_CLI_COMMAND, aggregate=True, optional=True)
class CLIRunner:
    def run(self, argv: list[str]) -> int: ...
```

## API Server 自动拉起

`APIGuard` 负责检测 API server 是否监听：

```python
class APIGuard:
    def ensure_api_server(self, base_url: str) -> None: ...
```

流程：

1. 请求 `GET {base_url}/health`
2. 如果返回成功，直接继续
3. 如果连接失败，启动 `uvicorn` 子进程运行 API server
4. 轮询 `/health`，直到服务就绪或超时
5. 超时抛出 `RuntimeError`

## 默认命令插件

- `TemplateHealthCommandPlugin`：提供 `health` 子命令
- 执行前调用 `APIGuard.ensure_api_server()`
- 然后请求 `/health` 并打印结果

## 动态加载

- 新 CLI 命令以 Pelix bundle / iPOPO component 形式注册
- 安装后，`CLIRunner` 重建 argparse parser
- 卸载后，命令从 parser 中消失

## 测试与验收

### 单元测试

- command provider 协议
- parser 注册逻辑
- APIGuard 检测已监听端口
- APIGuard 自动启动子进程
- CLI runner 执行命令

### e2e 测试

- 启动真实 Pelix/iPOPO 框架
- 安装 `health` 命令插件
- 不启动 API server，直接执行 CLI，验证自动拉起
- 启动 API server 后执行 CLI，验证复用已运行服务
- 动态安装/卸载命令插件，验证子命令变化

### 覆盖率

- 单元测试覆盖率 >= 95%
- 每个功能都有 e2e 测试

## 实施顺序

1. 创建 `langharness_cli` 包与 contracts
2. TDD 实现 `APIGuard`
3. TDD 实现 `CLIRunner`
4. 实现 `TemplateHealthCommandPlugin`
5. 完成 e2e
6. `make check` 并提交

## 待确认

- API server 默认地址是否使用 `http://127.0.0.1:8000`
- 自动拉起采用子进程 `uvicorn` 还是线程内嵌启动
- CLI 子命令解析是否使用 `argparse`，还是引入 `typer`
