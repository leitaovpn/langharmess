# 仓库压缩脚本设计方案（scripts/archive_repo.sh）

## 目标

新增 `scripts/archive_repo.sh`，把当前仓库打包成单个 zip 快照：**工作区当前
状态下的 git 跟踪文件 + 完整 `.git`（全部历史）**，不含未跟踪/被忽略文件
（`.venv/`、缓存、`*.sqlite3`、`.coverage` 等）。用于备份、迁移或交付当前
工作状态而不丢未提交改动。

## 用法

```bash
scripts/archive_repo.sh [输出路径.zip]
```

- 默认输出 `<仓库根>/dist/<仓库目录名>-<YYYYmmdd-HHMMSS>.zip`（目录不存在则
  创建）；`dist/` 已被 `.gitignore` 忽略，快照不会污染自身。
- 传入位置参数时覆盖默认输出；相对路径按调用者的当前目录解析。
- 依赖 `git`、`zip`（Info-ZIP）、`unzip`，缺失或不在 git 仓库内即前置报错
  非零退出。

## 归档布局

所有条目统一加一层 `<仓库目录名>/` 前缀：

```text
langharness-main/README.md
langharness-main/src/...
langharness-main/.git/...
```

解压得到单一目录，`git status` / `git log` 在解压目录内直接可用。

## 行为要点

1. **文件清单**：`git ls-files -z` 取索引中的跟踪文件，NUL 分隔；过滤掉
   「索引中有、磁盘上已删除」的未 staged 删除，与工作区状态语义一致；
   条目加 `<仓库名>/` 前缀后经 `xargs -0` 交给 `zip`，中文/空格文件名安全。
2. **`.git`**：从仓库父目录 `zip -r` 追加整棵 `.git`；不 gc、不 shallow、
   不改动仓库。
3. **原子替换**：先写 `<输出>.tmp.$$`，`unzip -t` 验证完整性后再 `mv` 原子
   替换目标文件——避免 zip 更新模式在旧归档中残留已删除文件的条目；`trap`
   在失败时清理临时文件。
4. **输出**：结束后打印归档路径、条目数、压缩后大小。
5. **不做修改性操作**：脚本对仓库只读。

## 实现框架（bash，set -euo pipefail）

结构与 `scripts/build_packages.sh` 一致：

```bash
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
```

从 `$(dirname "$PROJECT_ROOT")` 运行 zip，以 `<仓库名>/<相对路径>` 形式喂入
条目，保证归档内的前缀目录。

## 测试与验收

新增 `tests/test_archive_repo_script.py`（pytest + subprocess，临时 git 仓库
fixture）：

- 中文名、含空格文件名正确入档且解压恢复；
- 未提交修改以工作区内容入档；
- 未 staged 删除的跟踪文件被跳过；
- 未跟踪文件不在归档内；
- `.git` 完整：解压后 `git log` / `git status` 可用；
- 默认输出名符合 `<仓库名>-<时间戳>.zip`，显式输出参数生效；
- 非 git 目录、依赖缺失时非零退出且无残留临时文件。

## 明确不做

- 不处理 submodule（当前仓库无）；
- 不 gc / shallow / 改动仓库，不做加密、分卷；
- 不做压缩级别、过滤规则等可调开关。
