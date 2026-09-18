# langharness_api 插件化 API Server 设计方案

## 目标

在 `src/langharness_api` 中实现一个基于 FastAPI 的插件化 API Server，能力包括：

- 身份鉴权插件
- 限流插件
- DB 插件
- 每个 API 接口都是一个插件
- 运行时动态扩展能力

本方案复用现有 `langharness_plugin` 的 `PluginManager` / `PluginRegistry` 和
`langharness_core` 的服务规范模式。

## 包结构

```text
src/langharness_api/
├── __init__.py
├── contracts.py
├── app.py
└── plugins/
    ├── __init__.py
    ├── auth/
    │   └── template_auth.py
    ├── rate_limit/
    │   └── template_rate_limit.py
    ├── db/
    │   └── template_db.py
    └── routes/
        └── template_health.py
```

## 服务规范

```python
SPEC_API_SERVER = "api.server"
SPEC_AUTH = "api.plugin.auth"
SPEC_RATE_LIMIT = "api.plugin.rate_limit"
SPEC_DB = "api.plugin.db"
SPEC_ROUTE = "api.plugin.route"
```

## 插件契约

### RouteProvider

```python
class RouteProvider(Protocol):
    def get_router(self) -> APIRouter: ...
    def get_plugin_info(self) -> dict[str, str]: ...
```

### AuthProvider

```python
class AuthProvider(Protocol):
    def get_auth_dependency(self) -> Callable[[Request], AuthContext]: ...
    def get_plugin_info(self) -> dict[str, str]: ...
```

### RateLimitProvider

```python
class RateLimitProvider(Protocol):
    def get_rate_limit_dependency(self) -> Callable[[Request], None]: ...
    def get_plugin_info(self) -> dict[str, str]: ...
```

### DBProvider

```python
class DBProvider(Protocol):
    def get_session_dependency(self) -> Callable[[], Any]: ...
    def get_plugin_info(self) -> dict[str, str]: ...
```

## API Server 组装

`APIServerService` 是一个 iPOPO 组件：

```python
@ComponentFactory("api-server-factory")
@Provides(SPEC_API_SERVER)
@Requires("_route_providers", SPEC_ROUTE, aggregate=True, optional=True)
@RequiresBest("_auth_provider", SPEC_AUTH, optional=True)
@RequiresBest("_rate_limit_provider", SPEC_RATE_LIMIT, optional=True)
@RequiresBest("_db_provider", SPEC_DB, optional=True)
class APIServerService:
    def build_app(self) -> FastAPI: ...
```

`build_app()` 流程：

1. 创建 `FastAPI(title="langharness_api", version="0.1.0")`
2. 如果存在 DB 插件，注册 session dependency 到全局 override
3. 如果存在鉴权插件，生成 auth dependency
4. 如果存在限流插件，生成 rate-limit dependency
5. 遍历所有 route provider，获取 `APIRouter` 并 `include_router`
6. 所有路由统一挂载 `dependencies=[auth_dependency, rate_limit_dependency]`

当 route/auth/rate/db 插件绑定或解绑时，`@BindField` / `@UnbindField` 触发重建新的
FastAPI app。

## 动态扩展

- 每个路由插件只暴露自己的 `APIRouter`。
- `APIServerService` 聚合所有 route provider。
- 新路由插件安装后，Agent/API Server 重建 app，包含新路由。
- 路由插件卸载后，重建 app 移除对应路由。
- 鉴权、限流、DB 插件使用 `@RequiresBest`，默认选择最高 `service.ranking`。

## 默认模板插件

先提供参考实现模板：

- `TemplateAuthPlugin`：读取 `Authorization: Bearer <token>`，校验失败抛 401。
- `TemplateRateLimitPlugin`：内存滑动窗口，超过阈值抛 429。
- `TemplateDBPlugin`：内存 SQLite/内存存储，暴露 session dependency。
- `TemplateHealthRoutePlugin`：提供 `GET /health`。

这些模板用于验证设计，不承载生产业务。

## 错误处理

- 401：鉴权插件抛 `HTTPException(401)`
- 429：限流插件抛 `HTTPException(429)`
- 500：统一 exception handler 记录错误
- 404：未注册路由由 FastAPI 默认处理

## 测试与验收

### 单元测试

- 每个 plugin getter / dependency 逻辑
- `APIServerService.build_app()` 组装逻辑
- 动态 route provider 绑定/解绑后的 app 路由变化

### e2e 测试

使用 `fastapi.testclient.TestClient`：

- 启动真实 Pelix/iPOPO 框架
- 安装 auth、rate limit、db、health route 插件
- 验证未认证请求返回 401
- 验证正确 token 返回 200
- 验证超过限流阈值返回 429
- 验证 DB dependency 可用
- 验证动态安装新 route plugin 后，新接口可访问
- 验证卸载 route plugin 后，接口消失

### 覆盖率

- 最终单元测试覆盖率 >= 95%
- 每个功能都有 e2e 测试

## 实施顺序

1. 创建 `langharness_api` 包与 contracts
2. TDD 实现 API server 组装逻辑
3. 实现四个模板插件
4. 完成 e2e 测试
5. 跑通 `make check` 并提交

## 待确认

- 鉴权默认方案是否使用 Bearer token
- 限流默认策略是否使用内存滑动窗口
- DB 插件默认是否使用 SQLite 内存库

## 验收矩阵

| 功能 | 成功标准 | e2e 验证 |
| --- | --- | --- |
| 身份鉴权插件 | 缺少或错误 token 返回 401；正确 token 放行 | `test_auth_e2e.py` |
| 限流插件 | 超过配置阈值返回 429；未超限放行 | `test_rate_limit_e2e.py` |
| DB 插件 | 路由中可注入 DB dependency，并读取/写入测试数据 | `test_db_e2e.py` |
| API 接口插件 | 安装 route plugin 后接口可访问 | `test_route_e2e.py` |
| 动态扩展 | 安装新 route plugin 后路由出现；卸载后路由消失 | `test_dynamic_route_e2e.py` |

## 关键接口签名草案

```python
class RouteProvider(Protocol):
    def get_router(self) -> APIRouter: ...

class AuthProvider(Protocol):
    def get_auth_dependency(self) -> Callable[[Request], AuthContext]: ...

class RateLimitProvider(Protocol):
    def get_rate_limit_dependency(self) -> Callable[[Request], None]: ...

class DBProvider(Protocol):
    def get_session_dependency(self) -> Callable[[], Any]: ...
```

## 开发边界

- 不修改 `langharness_core` / `langharness_plugin` 现有行为
- 新代码只落在 `src/langharness_api`、测试和本设计文档
- 先 TDD，再实现；每个功能必须有 e2e 测试
- 最终 `make check` 必须通过，覆盖率 >= 95%
