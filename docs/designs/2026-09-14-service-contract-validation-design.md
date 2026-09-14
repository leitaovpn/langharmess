# 服务契约校验设计方案（类规格 + 双侧签名校验）

## 目标

iPOPO 支持用 Protocol/类声明服务规格，但不做任何运行时方法签名校验。本方案让
**插件提供方在安装时被硬校验、消费方在服务绑定时被软校验**：服务对象必须包含
契约声明的全部方法，且入参、返回注解按「调用兼容性」标准符合预期。

- 判定标准：调用兼容性（consumer 能按协议声明的方式调用到 provider 即通过），
  不是逐字精确匹配。
- 触发点：安装侧硬拦（违规服务不进入注册表并抛错）+ 绑定侧兜底隔离
  （违规 provider 被摘出聚合、记 ERROR，系统继续运行）。
- 迁移方式：`@Provides/@Requires*` 的规格参数从 `SPEC_X` 字符串改为 Protocol 类，
  用 `__SPECIFICATION__` pin 住原服务名，服务名与注册表 JSON 不变。

## 关键事实（已在本仓库 .venv 的 iPOPO 3.x 上验证）

- `_get_specifications()`（`pelix/ipopo/decorators.py`）接受类：读取类上的
  `__SPECIFICATION__` 字段得到规格名；缺省则用 `__name__`
  （`Provides.USE_MODULE_QUALNAME=False`）。`@Provides(LLMProvider)` /
  `@Requires(field, LLMProvider)` 最终都归一为字符串规格，**运行时解析行为与
  现状完全一致**。Pelix 侧 `register_service()` / `get_service_reference()`
  同样识别 `__SPECIFICATION__`（`pelix/framework.py`）。
- 在 Protocol **类体内**写 `__SPECIFICATION__` 会进入 `__protocol_attrs__`，
  使 `isinstance(x, Protocol)` 要求实例携带该属性而失效。`__protocol_attrs__`
  在类创建时算好，因此**类创建后由装饰器赋值是安全的**（已验证
  `isinstance` 与 `_get_specifications` 均正常）。规则：只允许通过装饰器 pin。
- iPOPO 工厂元数据只保留规格**字符串**，不保留类对象；安装侧需要
  `规格名 → Protocol` 的运行时注册表，由装饰器自动登记。
- `@Validate` 回调发生在服务注册**之前**（`ProvidesHandler.post_validate`
  才注册服务），且 `ipopo.instantiate()` 返回组件实例——安装侧可以在服务
  对外可见之前拿到实例做硬校验。
- `@BindField` 回调里抛出的异常会被 iPOPO **吞掉**，消费侧不能靠抛错拒收，
  只能隔离。

## 组件一：契约声明（`service_contract`）

新增 `src/langharmess_plugin/validation.py`（框架层，纯 Python，不 import
iPOPO/pelix）：

```python
CONTRACTS: dict[str, type] = {}

def service_contract(spec_name: str):
    """把 Protocol 钉为 Pelix 规格名，并登记进 CONTRACTS。"""
    def decorate(cls: type) -> type:
        cls.__SPECIFICATION__ = spec_name
        existing = CONTRACTS.get(spec_name)
        if existing is not None and existing is not cls:
            raise ValueError(f"specification {spec_name!r} already pinned")
        CONTRACTS[spec_name] = cls
        return cls
    return decorate

def contract_for(specification: str) -> type | None: ...
```

用法（各模块 `contracts.py`）：

```python
SPEC_LLM = "agent.plugin.llm"

@service_contract(SPEC_LLM)
@runtime_checkable
class LLMProvider(Protocol):
    def get_model(self) -> BaseChatModel: ...
```

- `SPEC_*` 常量仍是服务名的唯一来源：descriptor、`ALL_PLUGIN_SPECS`、
  `get_service()` 查找都不动。
- 未 pin 的规格（第三方自有规格）不参与校验，`contract_for` 返回 None。
- 需要补齐的契约：`AgentLoopProvider`（`invoke` / `astream` / `describe`）、
  `APIServerProvider`（`build_app`）。`SPEC_CLI_RUNNER` 当前无消费者，不在本次范围。

## 组件二：校验语义（`validate` / `describe`）

`describe(protocol)` 用 `inspect.signature` + `typing.get_type_hints` 提取期望
签名（剥 `self`，只取可调用成员，结果缓存）。`validate(instance, protocol)`
返回 `Violation(spec, protocol, method, code, detail)` 元组：

| 违规码 | 判定 |
| --- | --- |
| `MISSING_METHOD` / `NOT_CALLABLE` | 契约方法不存在或不可调用 |
| `PARAM_NOT_ACCEPTED` | 契约参数 provider 接不住（无同名同种类参数，也无 `*args`/`**kwargs` 可吸收） |
| `PARAM_KIND_CONFLICT` | 同名参数但种类不兼容（如契约位置传递、provider 仅关键字） |
| `PARAM_EXTRA_REQUIRED` | provider 有契约之外的必填参数（无默认值） |
| `PARAM_ANNOTATION_MISMATCH` | provider 已声明参数注解且与协议冲突（协议 `Any` 跳过；未声明容忍） |
| `RETURN_ANNOTATION_MISSING` | 契约有返回注解，provider 未声明 |
| `RETURN_ANNOTATION_MISMATCH` | 注解归一后不一致 |
| `UNRESOLVED_SIGNATURE` | `get_type_hints` 解析失败（前向引用断裂），要求修契约而非静默放过 |

注解归一：`typing.get_origin/get_args` 递归比较，协议侧 `Any` 为通配，
`X | None ≡ Optional[X]`，`list[Any]` 的 args 通配。非可调用成员（数据属性）
不参与校验。校验失败聚合为 `ContractViolationError(RuntimeError)`，消息形如：

```text
plugin 'runtime-llm' violates 'agent.plugin.llm' (LLMProvider):
  get_model: RETURN_ANNOTATION_MISMATCH (BaseChatModel != object)
```

## 组件三：安装侧硬拦（PluginManager）

`_instantiate` 拿到实例后按 descriptor 的规格查找契约；违规则 kill 实例、
抛错、不进 `_bound`，服务从未进入注册表：

```python
instance = self._ipopo.instantiate(descriptor.factory, descriptor.instance, props)
protocol = contract_for(descriptor.specification)
if protocol is not None:
    violations = validate(instance, protocol)
    if violations:
        self._ipopo.kill(descriptor.instance)
        raise ContractViolationError(descriptor.name, descriptor.specification, violations)
self._bound.add(descriptor.name)
```

`/stream` 路由在 `ensure_plugin(runtime_llm_descriptor)` 处捕获
`ContractViolationError` → HTTP 400 + 归因消息（运行时 LLM 插件由请求体拼装，
用户输入错误应得到 400 而非 500）。

## 组件四：绑定侧兜底（ContractGuard）

`ContractGuard` 与本方案其他工具同在 `langharmess_plugin/validation.py`，纯
Python 不依赖 iPOPO。绕过 PluginManager 直接注册的服务没有安装侧校验，
消费方在 bind 回调兜底：

```python
# __init__
self._tools = ContractGuard(self, "_tool_providers", ToolProvider)

@BindField("_tool_providers", if_valid=True)
def _on_tool_bind(self, field, service, reference):
    if not self._tools.admit(service):
        return
    self._rebuild()

@UnbindField("_tool_providers", if_valid=True)
def _on_tool_unbind(self, field, service, reference):
    self._tools.release(service)
    self._rebuild()
```

`admit()` 违规时：记 ERROR（含 violations 详情）、把服务从 owner 的聚合列表
摘除（best 字段置 None，等价于无此服务）、登记进 `rejected`（供测试与排查），
返回 False。守卫字段：agent_loop 15 个、api server app 6 个、stream 路由 2 个、
configs 1 个。

## 迁移清单

- contracts.py 加 pin：`langharmess_core` 15 个、`langharmess_api` 4 个、
  `langharmess_cli` 2 个、`langharmess_config` 2 个、`langharmess_logging` 1 个、
  `langharmess_plugin`（`PluginRegistrar`）1 个；补 `AgentLoopProvider`、
  `APIServerProvider`；`examples/plugin_demo/contracts.py` 同步。
- 声明替换 `SPEC_X → Protocol 类`：src 32 处 `@Provides`、24 处
  `@Requires/@RequiresBest`，examples 7 处。
- `PluginManager.start` 的 `register_service` 改用 `PluginRegistrar` 类。
- 上述 24 个消费字段接 `ContractGuard`；`/stream` 路由加 400 处理。
- `AGENTS.md` 增一条规则：新增/修改服务契约必须 `@service_contract` pin，
  组件声明一律用 Protocol 类，不得在 Protocol 类体内写 `__SPECIFICATION__`。

## 测试与验收

- 单测：签名提取（含 `from __future__ import annotations` 字符串注解）、
  `*args/**kwargs` 吸收、`PARAM_EXTRA_REQUIRED`、位置/关键字种类冲突、
  返回注解归一（`list[Any]`、`X | None`、`Any` 通配）、缺失方法、注解无法解析；
  `ContractGuard` 摘除/best 置 None/release/rejected；`service_contract`
  同名重复 pin 抛错、pin 后 `__SPECIFICATION__ not in __protocol_attrs__`。
- 安装侧：坏组件 → 实例被 kill、注册表查不到该服务、抛
  `ContractViolationError`；未 pin 规格跳过校验。
- e2e：绕过 PluginManager 直接 `register_service` 注册坏服务 → 消费方隔离且
  系统继续；现有三协议 e2e 与 `make check` 全绿（覆盖率门禁 95% 不变）。
- 回归：pin 名 == 原 `SPEC_*` 字符串（`get_service_reference("agent.plugin.llm")`
  仍命中）；`isinstance` 语义不被污染。

## 明确不做

- 不做调用期代理校验（实参/返回值运行时类型检查），需要时作为第三层叠加。
- 不做 per-descriptor 的校验策略逃生阀（v1 统一策略，靠「不 pin 即不校验」豁免）。
- 不迁移 `get_service()/ALL_PLUGIN_SPECS` 等字符串查找点（常量即 pin，保持现状）。
- 不清理 `SPEC_CLI_RUNNER` 等无消费者常量。
