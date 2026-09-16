# 问题复现脚本

对应 `docs/problem/2026-09-16-*.md` 三个问题记录，均可用
`.venv/bin/python <script>` 直接运行（除注明外不需要外部凭据）。

| 脚本 | 对应问题 | 说明 |
|------|----------|------|
| `repro_loop_death.py` | agent-loop-permanent-death | 假 LLM + 真实 API server 子进程；S1 带凭据 → S2 省略凭据 → 503，S3 仍 503。确定性复现 loop 永久死亡 |
| `repro_delta_drop.py` | stream-delta-drop | 假 LLM 按 chunk 依次发 `["scope","-marker","-","7","7"]`，`/stream` 只转发 `scope-marker-7`。确定性复现重复 delta 被吞 |
| `repro_bare_sdk.py` | responses-protocol-gateway-500 | 需在含 `langharmess.toml`（`[providers.chatgpt-5]`）的目录下运行，用裸 openai SDK 对比 `/responses`（500）与 `/chat/completions`（正常）。会真实请求外部网关，按需运行 |

## 注意事项

- 前两个脚本会自行在 `$TMPDIR` 建隔离工作区并拉起/回收 uvicorn 子进程，不污染 `~/.langharmess`；
- `repro_loop_death.py` / `repro_delta_drop.py` 依赖 `tests/fixtures/fake_llm_server.py`（通过 `sys.path` 挂载 `tests/`）；
- `repro_bare_sdk.py` 会消耗真实网关配额，且把 provider 的 api_key 读出到内存（不落盘）。
