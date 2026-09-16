# responses 协议在阿里云 MaaS compatible-mode 网关不可用（500）

日期：2026-09-16
状态：外部网关缺陷，待配置规避（建议 protocol 改 chat）

## 现象

`~/.langharmess/langharmess.toml` 中 `chatgpt-5` provider 配置为
`protocol="responses"` + `base_url="…/compatible-mode/v1"` + `model="qwen-max"`。
真实 CLI 运行中每个请求都失败：

```text
Error code: 500 - {'request_id': …, 'error': {'code': 'InvalidParameter',
'type': 'invalid_request_error', 'message': "1 validation error for Event\nobject\n
Field required [type=missing, input_value={'finish_reason': 'null', 'text': 'Hello'},
input_type=dict]"}}
```

错误里回显的 `'Hello'` 是我们自己的输入内容 —— 网关把请求翻译成内部
Event 对象时漏填了必填的 `object` 字段。

## 最小复现

裸 openai SDK，不涉及任何本项目代码（`docs/problem/repro/repro_bare_sdk.py`，
需在含 `langharmess.toml` 的目录下运行）：

```python
client = AsyncOpenAI(api_key=…, base_url=…/compatible-mode/v1)
await client.responses.create(model="qwen-max", input="Hello")   # → 500 同上
await client.chat.completions.create(model="qwen-max", …)        # → 正常返回
```

- stream / 非 stream 都失败；
- qwen-max / qwen3-vl-32b-thinking / qwen-plus-2025-07-28 三个模型都失败；
- 同一网关同一模型的 `/chat/completions` 正常。

本项目侧请求体经 dump 验证是干净的（`model` + `input` 消息数组），
问题不在 langharmess / langchain-openai 的请求构造。

## 结论与影响

- **网关的 Responses API 翻译层缺陷**：其内部 Event 模型要求 `object`
  字段，而它自己的转换器没有填。对任何 Responses 请求都稳定 500。
- 该网关下 `protocol="responses"` 完全不可用，真实链路从未跑通过；
  `responses` 协议代码路径只能靠 fake LLM 测试覆盖。
- 产品把原始上游 500 透传给 CLI 用户，无任何可操作提示。

## 规避与改进建议

1. 配置规避：该网关的 provider 改为 `protocol="chat"`（已验证可用）；
   `responses` 协议只有在真正实现 Responses API 的端点上才能使用。
2. 产品侧可选：配置加载时对 `protocol="responses"` + compatible-mode
   网关给出提示；或对上游错误附加「协议/网关不兼容」的上下文信息。
