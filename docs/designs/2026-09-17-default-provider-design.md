# 配置文件默认模型（providers.default）设计方案

## 目标

- 配置文件增加默认模型配置：`[providers.default]` 段。
- 交互模式启动时不再从 providers 中随机选择，改用 `providers.default`。
- 未配置默认模型时，交互模式直接报错退出，不再回落到随机选择或环境变量。

## 语义

`default` 是 `[providers]` 下的保留名称，仅用于启动时的默认模型：

- 交互模式未显式传 `--provider` 时，使用 `providers.default`。
- `default` 不出现在 `/model` 列表中。
- `--provider default` 与 `/model default` 均被拒绝（用户只能切换到其他具名
  provider）。
- `default` 段缺失、为空或校验失败（protocol/model/api_key/base_url）时，
  交互模式打印错误到 stderr 并以退出码 2 退出。
- 显式 `--provider <name>` 仍不需要默认模型；非交互子命令不受影响。

## 配置模板

`src/langharmess_config/config/langharmess.toml` 与 `scripts/install.sh` 中
写入的模板：删除现有的激活占位段 `[providers.deepseek-v4-flash]`，改为注释
示例（新装环境因此报错，提示用户配置）：

```toml
# Default model used when interactive mode starts without --provider.
# [providers.default]
# protocol = "chat"
# base_url = "https://api.example.com/v1"
# model = "your-model"
# api_key = "your-api-key"
```

## 契约与实现

- `Configs` 协议（`src/langharmess_config/contracts.py`）新增
  `get_default_provider() -> Mapping[str, Any]`。
- `ConfigsPlugin`（`src/langharmess_config/plugins/configs.py`）：
  - 抽取 `get_provider` 的校验逻辑为 `_validated_provider(name, provider)`
    私有辅助方法，`get_provider` 与 `get_default_provider` 共用。
  - `get_default_provider()`：读取 `providers.default`（经 `get_section`，
    保留 `[DEFAULT]` 合并语义）；缺失或为空时抛
    `ValueError("No default model is configured: add a [providers.default] section to langharmess.toml")`；
    否则按普通 provider 校验后返回。
  - `get_provider("default")` 抛
    `ValueError("Provider name 'default' is reserved for the default model")`。
  - `list_providers()` 排除 `default`。
- `src/langharmess_cli/common/cli.py` 交互分支：
  - 无 `--provider` 且存在 configs 服务：调用 `get_default_provider()`，
    失败（ValueError）打印 stderr、返回 2；成功后用其
    model/api_key/base_url/protocol，`provider_name="default"`。
  - 显式 `--provider`：`get_provider` 调用包 `try/except ValueError`
    （同时修复今天 `--provider` 指向非法 protocol 时直接 traceback 的问题），
    失败打印 stderr、返回 2；返回空 dict 维持现有 "Unknown provider" 处理。
  - `configs` 服务缺失时维持现有环境变量回退路径。
  - 移除 `import random`。

## 测试

- `tests/test_config.py`：
  - 模板测试改为断言无激活 providers（注释段不产生 `providers` 键）。
  - 新增：`get_default_provider` 缺失/为空/非法时报 ValueError、合法时返回
    校验后的配置、`get_provider("default")` 保留名拒绝、
    `list_providers()` 排除 `default`。
  - `test_configs_service_aggregates_toml_plugin_in_ipopo` 改为预写含
    `[providers.default]` 的配置文件后断言。
- `tests/test_cli.py`：
  - 随机选择测试替换为“无 --provider 时使用默认 provider”测试。
  - `test_main_survives_broken_provider_config` 的配置中补充
    `default` provider（broken 项不影响启动）。
  - 新增：缺少默认 provider 时 main 返回 2 且 stderr 有提示；
    `--provider default` 返回 2。
- `tests/test_packaging.py`：installer 断言更新为注释示例内容。

## 文档

- `README.md`：模板示例、`--provider` 示例与“随机选择”段落更新。
- `AGENTS.md`：删除“随机选择 provider”的开发提示。

## 非目标

- server 模式不消费 provider 配置，本次不改。
- 不新增 provider 指针（如 `[DEFAULT] default_provider = "name"`）机制。
