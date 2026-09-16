# 流式文本静默丢失重复 delta 块

日期：2026-09-16
状态：已修复（agent_loop.py 按累积前缀判断 chunk 模式，回归测试 + 真实 CLI 复验通过）

## 现象

真实 CLI 端到端测试中（provider deepseek-v4-flash，chat 协议），让模型记住
`scope-marker-77`，CLI 两次渲染成 `scope-marker-7`（少一个 `7`）；直接抓取
`POST /stream` 的 NDJSON 事件同样只收到 `"scope" + "-marker" + "-" + "7"`，
而 checkpoint（服务端聚合的完整消息）是**正确**的 `scope-marker-77`。

即：客户端看到的流式文本被静默截断、无任何报错，但会话记忆是对的 ——
两个数据源不一致，属于数据损坏。

## 最小复现

用一个假 LLM 按流式 chunk 依次返回 `["scope", "-marker", "-", "7", "7"]`
（拼接后等价于 `scope-marker-77`），经 `/stream` 转发出来的 assistant 事件
拼起来是 `scope-marker-7` —— 第二个 `"7"` chunk 被吞。100% 稳定复现。

完整脚本（含假 LLM chunk 服务器 + 真实 API server + /stream 采集）：
`docs/problem/repro/repro_delta_drop.py`。核心是让 provider 发出两个**连续相同**
的 delta chunk。

## 根因

`src/langharmess_core/plugins/loop/agent_loop.py:601`（`astream` 的消息转发）：

```python
previous = previous_content.get(message_id, "")
delta = content[len(previous) :] if content.startswith(previous) else content
previous_content[message_id] = content
if delta:
    yield {"type": "assistant", "content": delta}
```

这段前缀切片假设 chunk 内容是**累积式**（cumulative）的。但 chat 协议的
流式 chunk 是**增量式**（delta）的：当某个 chunk 恰好等于或以「上一个
chunk」开头（最常见的就是两个连续相同 token，如 `"7"`,`"7"`、`"**"`,`"**"`），
`startswith` 命中，delta 切成空串，`if delta:` 直接丢弃该 chunk。

另外 `previous_content[message_id]` 存的是**最后一个 chunk** 而非累积文本，
进一步扩大误判面（前一个 delta 是后一个 delta 的前缀时同样出错）。

anthropic 协议（`ChatAnthropic`）的 chunk 内容是累积式的，因此不受影响 ——
与本测试中只有 chat 协议出现该问题一致。

## 影响

- chat 协议下所有客户端（CLI / 直连 API）看到的流式文本都可能缺字符，
  出错位置取决于模型 token 切分，无任何错误提示；
- checkpoint 正确而流错误，事后排查时两处证据互相矛盾。

## 修复方向

按 message_id 维护**累积**文本，用累积前缀判断 chunk 模式：

```python
accumulated = previous_content.get(message_id, "")
if content.startswith(accumulated):      # 累积式：取后缀
    delta = content[len(accumulated) :]
else:                                    # 增量式：整体转发
    delta = content
previous_content[message_id] = accumulated + delta
if delta:
    yield {"type": "assistant", "content": delta}
```

两种协议模式都正确；另建议补一个假 LLM 发「两个连续相同 chunk」的回归测试
（对应 `tests/test_agent_loop_tool_fragments.py` 的同类做法）。

## 修复记录（2026-09-16）

- `agent_loop.py` astream 转发改为按 message_id 维护**累积文本**：chunk 以累积
  文本开头视为累积式取后缀，否则视为增量式整体转发。两种协议模式均正确。
- 新增回归测试 `tests/test_agent_loop_stream_deltas.py`（连续相同 delta 转发、
  累积式内容取后缀）。
- 真实 CLI 复验：chat + anthropic 两个协议下 `scope-marker-77` 均完整回显，
  多工具轮次正常。
