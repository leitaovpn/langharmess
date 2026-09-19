# 仓库压缩脚本实现计划（scripts/archive_repo.sh）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `scripts/archive_repo.sh`：把「工作区当前状态的 git 跟踪文件 + 完整 `.git`」打成单个 zip 快照（条目带 `<仓库名>/` 前缀），默认输出到 `<仓库根>/dist/`。

**Architecture:** bash（`set -euo pipefail`）+ Info-ZIP。`git ls-files -z` 出跟踪文件（工作区内容，跳过未 staged 删除），经 `xargs -0` 交给 `zip`；`zip -q -r` 追加整棵 `.git`；先写 `<输出>.tmp.$$`，`unzip -t` 校验后 `mv` 原子替换。

**Tech Stack:** bash、Info-ZIP zip/unzip 3.0、pytest（subprocess 端到端 + 临时 git 仓库 fixture）。

**设计文档:** `docs/designs/2026-09-14-repo-archive-script-design.md`

**已验证的前提（已在 /tmp 临时仓库实测，直接依赖，不要重复验证）:**
- Info-ZIP 3.0 按字面名匹配存在的文件：`a[1].txt` 不会被当通配符展开（同目录存在 `a1.txt` 也不误配）。
- `zip -q` 对列表中缺失的文件只告警不失败（全部缺失才 exit 12）→ 仍需自行过滤已删除文件，保证「跟踪文件全部删除」的仓库也能出档。
- `zip -q -r -y <archive> <名>/.git` 递归追加正常；`-y` 把符号链接存为链接（当前仓库无符号链接，为未来保真）。
- Info-ZIP 对中文名设置 UTF-8 标志位（`flag_bits & 0x800`），Python `zipfile` 与 `unzip` 解码/解压回环都正确。
- `unzip -tq <archive>` 成功时 exit 0；`unzip -l <archive> | tail -n 1` 汇总行格式 `"<bytes>  <N> files"`；`du -h <archive> | cut -f1` 取大小。
- 脚本用 `${BASH_SOURCE[0]}` 推导 `PROJECT_ROOT` → **测试必须把脚本拷贝到临时仓库的 `scripts/` 下运行**，否则会去打包真实仓库。

**每个 Task 最后跑 `make check`（仓库门禁：ruff → mypy → pyright → 干净进程导入 → pytest 覆盖率 95%）。命令一律在仓库根执行。**

---

## Task 1: 核心归档语义（跟踪文件工作区内容 + 完整 .git）

**Files:**
- Create: `tests/test_archive_repo_script.py`
- Create: `scripts/archive_repo.sh`

- [ ] **Step 1: 写失败测试（fixture + 5 个核心用例）**

创建 `tests/test_archive_repo_script.py`：

```python
"""End-to-end tests for scripts/archive_repo.sh."""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "archive_repo.sh"
REPO_NAME = "sample-repo"


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "tester")
    env.setdefault("GIT_AUTHOR_EMAIL", "tester@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "tester")
    env.setdefault("GIT_COMMITTER_EMAIL", "tester@example.com")
    return env


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=_git_env(),
    )


def _run_script(
    repo: Path, cwd: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / "scripts" / "archive_repo.sh"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=_git_env() if env is None else env,
    )


def _entries(archive: Path) -> set[str]:
    with zipfile.ZipFile(archive) as zf:
        return set(zf.namelist())


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / REPO_NAME
    (repo / "scripts").mkdir(parents=True)
    (repo / "sub").mkdir()
    (repo / "plain.txt").write_text("base\n", encoding="utf-8")
    (repo / "中文 文件.txt").write_text("中文内容\n", encoding="utf-8")
    (repo / "sub" / "nested.txt").write_text("deep\n", encoding="utf-8")
    (repo / "deleted.txt").write_text("old\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    (repo / "plain.txt").write_text("modified\n", encoding="utf-8")
    (repo / "deleted.txt").unlink()
    (repo / "untracked.txt").write_text("nope\n", encoding="utf-8")
    shutil.copy2(SCRIPT, repo / "scripts" / "archive_repo.sh")
    return repo


def test_archives_tracked_files_with_repo_prefix(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "snapshot.zip"
    completed = _run_script(repo, repo, str(out))
    assert completed.returncode == 0, completed.stderr
    entries = _entries(out)
    data_entries = {e for e in entries if not e.startswith(f"{REPO_NAME}/.git/")}
    assert data_entries == {
        f"{REPO_NAME}/plain.txt",
        f"{REPO_NAME}/sub/nested.txt",
        f"{REPO_NAME}/中文 文件.txt",
    }
    assert f"{REPO_NAME}/.git/HEAD" in entries
    assert f"{REPO_NAME}/.git/config" in entries


def test_archived_content_is_working_tree_state(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "snapshot.zip"
    completed = _run_script(repo, repo, str(out))
    assert completed.returncode == 0, completed.stderr
    with zipfile.ZipFile(out) as zf:
        assert zf.read(f"{REPO_NAME}/plain.txt") == b"modified\n"


def test_deleted_and_untracked_files_are_excluded(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "snapshot.zip"
    completed = _run_script(repo, repo, str(out))
    assert completed.returncode == 0, completed.stderr
    entries = _entries(out)
    assert not any(e.endswith("deleted.txt") for e in entries)
    assert not any(e.endswith("untracked.txt") for e in entries)


def test_chinese_and_space_filenames_roundtrip(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "snapshot.zip"
    completed = _run_script(repo, repo, str(out))
    assert completed.returncode == 0, completed.stderr
    dest = tmp_path / "extracted"
    with zipfile.ZipFile(out) as zf:
        assert zf.read(f"{REPO_NAME}/中文 文件.txt") == "中文内容\n".encode()
        zf.extractall(dest)
    restored = dest / REPO_NAME / "中文 文件.txt"
    assert restored.read_text(encoding="utf-8") == "中文内容\n"


def test_extracted_archive_is_usable_git_repository(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "snapshot.zip"
    completed = _run_script(repo, repo, str(out))
    assert completed.returncode == 0, completed.stderr
    dest = tmp_path / "extracted"
    with zipfile.ZipFile(out) as zf:
        zf.extractall(dest)
    clone = dest / REPO_NAME
    log = _git(clone, "log", "--oneline")
    assert "init" in log.stdout
    porcelain = _git(clone, "status", "--porcelain").stdout
    status = {line.strip() for line in porcelain.splitlines()}
    assert {"M plain.txt", "D deleted.txt"} <= status
```

- [ ] **Step 2: 跑测试，确认全部失败**

Run: `.venv/bin/python -m pytest tests/test_archive_repo_script.py -v`
Expected: 5 failed（`FileNotFoundError`：脚本尚不存在）

- [ ] **Step 3: 实现脚本最小版本**

创建 `scripts/archive_repo.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO_NAME=$(basename "$PROJECT_ROOT")
PARENT_DIR=$(dirname "$PROJECT_ROOT")

OUT=$1

mkdir -p "$(dirname "$OUT")"

# Working-tree content of tracked files; entries deleted on disk but not yet
# staged as deleted are skipped.
git -C "$PROJECT_ROOT" ls-files -z | while IFS= read -r -d '' path; do
  if [[ -e "$PROJECT_ROOT/$path" || -L "$PROJECT_ROOT/$path" ]]; then
    printf '%s\0' "$REPO_NAME/$path"
  fi
done | (cd "$PARENT_DIR" && xargs -0 -r zip -q -y "$OUT")

(cd "$PARENT_DIR" && zip -q -r -y "$OUT" "$REPO_NAME/.git")
```

- [ ] **Step 4: 加执行位并跑测试，确认全部通过**

Run: `chmod +x scripts/archive_repo.sh && .venv/bin/python -m pytest tests/test_archive_repo_script.py -v`
Expected: 5 passed

- [ ] **Step 5: 跑仓库门禁**

Run: `make check`
Expected: ruff / mypy / pyright / 导入检查 / pytest（覆盖率 ≥95%）全绿

- [ ] **Step 6: 提交**

```bash
git add scripts/archive_repo.sh tests/test_archive_repo_script.py
git commit -m "新增 archive_repo.sh：打包工作区跟踪文件与完整 .git 为 zip"
```

---

## Task 2: CLI 契约与原子替换（默认输出、参数校验、依赖/仓库检查、unzip -t 校验）

**Files:**
- Modify: `scripts/archive_repo.sh`（替换为最终版）
- Modify: `tests/test_archive_repo_script.py`（import 增加 `re`；追加 5 个用例）

- [ ] **Step 1: 追加失败测试**

在 `tests/test_archive_repo_script.py` 顶部 import 块中，把 `import os` 下一行插入 `import re`（保持字母序：`os`、`re`、`shutil`、`subprocess`、`zipfile`），文件末尾追加：

```python
def test_default_output_path_and_name(repo: Path, tmp_path: Path) -> None:
    completed = _run_script(repo, repo)
    assert completed.returncode == 0, completed.stderr
    produced = sorted((repo / "dist").glob(f"{REPO_NAME}-*.zip"))
    assert len(produced) == 1
    assert re.fullmatch(rf"{REPO_NAME}-\d{{8}}-\d{{6}}\.zip", produced[0].name)
    assert str(produced[0]) in completed.stdout
    assert "entries:" in completed.stdout
    assert "size:" in completed.stdout
    assert not list((repo / "dist").glob("*.tmp.*"))


def test_relative_output_resolves_against_caller_cwd(repo: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    completed = _run_script(repo, elsewhere, "rel.zip")
    assert completed.returncode == 0, completed.stderr
    assert (elsewhere / "rel.zip").is_file()
    assert str(elsewhere / "rel.zip") in completed.stdout


def test_rejects_extra_arguments(repo: Path, tmp_path: Path) -> None:
    completed = _run_script(repo, repo, "one.zip", "two.zip")
    assert completed.returncode != 0
    assert not (repo / "one.zip").exists()


def test_fails_outside_git_repository(tmp_path: Path) -> None:
    scripts = tmp_path / "not-a-repo" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(SCRIPT, scripts / "archive_repo.sh")
    completed = subprocess.run(
        [str(scripts / "archive_repo.sh"), str(tmp_path / "out.zip")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    assert completed.returncode != 0
    assert "error: not a git repository" in completed.stderr
    assert not (tmp_path / "out.zip").exists()
    assert not list(tmp_path.glob("*.tmp.*"))


def test_fails_when_zip_is_missing(repo: Path, tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("bash", "git"):
        target = shutil.which(name)
        assert target is not None
        (bin_dir / name).symlink_to(target)
    env = _git_env()
    env["PATH"] = str(bin_dir)
    completed = _run_script(repo, repo, str(tmp_path / "out.zip"), env=env)
    assert completed.returncode != 0
    assert "required command not found: zip" in completed.stderr
```

- [ ] **Step 2: 跑测试，确认新用例失败、旧用例仍通过**

Run: `.venv/bin/python -m pytest tests/test_archive_repo_script.py -v`
Expected: 5 failed（默认输出：0 参数下 `$1` 未绑定而退出；多余参数：仍出档；相对路径：落到父目录；非 git：报错文案是 git 的 `fatal:`；缺 zip：`dirname` 缺失先失败）、5 passed

- [ ] **Step 3: 替换脚本为最终版**

`scripts/archive_repo.sh` 全文替换为：

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 1 ]]; then
  echo "usage: ${0##*/} [output.zip]" >&2
  exit 1
fi

for cmd in git zip unzip; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "error: required command not found: $cmd" >&2
    exit 1
  fi
done

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO_NAME=$(basename "$PROJECT_ROOT")
PARENT_DIR=$(dirname "$PROJECT_ROOT")

if [[ $# -eq 1 ]]; then
  case "$1" in
    /*) OUT=$1 ;;
    *) OUT=$(pwd)/$1 ;;
  esac
else
  OUT="$PROJECT_ROOT/dist/${REPO_NAME}-$(date +%Y%m%d-%H%M%S).zip"
fi

if ! git -C "$PROJECT_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  echo "error: not a git repository: $PROJECT_ROOT" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"
TMP="$OUT.tmp.$$"
trap 'rm -f "$TMP"' EXIT

# Working-tree content of tracked files; entries deleted on disk but not yet
# staged as deleted are skipped.
git -C "$PROJECT_ROOT" ls-files -z | while IFS= read -r -d '' path; do
  if [[ -e "$PROJECT_ROOT/$path" || -L "$PROJECT_ROOT/$path" ]]; then
    printf '%s\0' "$REPO_NAME/$path"
  fi
done | (cd "$PARENT_DIR" && xargs -0 -r zip -q -y "$TMP")

(cd "$PARENT_DIR" && zip -q -r -y "$TMP" "$REPO_NAME/.git")

unzip -tq "$TMP" >/dev/null
mv -f "$TMP" "$OUT"

printf 'archive: %s\n' "$OUT"
printf 'entries: %s\n' "$(unzip -l "$OUT" | tail -n 1 | awk '{print $(NF-1), $NF}')"
printf 'size: %s\n' "$(du -h "$OUT" | cut -f1)"
```

要点（相对 Task 1 版本的增量）：依赖检查先于一切（`dirname`/`basename` 属外部命令，必须在 PATH 正常时已通过检查）；`${0##*/}` 代替 `basename "$0"`（纯 bash）；输出路径在调用者 cwd 下绝对化；默认输出 `<仓库根>/dist/<仓库名>-<年月日>-<时分秒>.zip`；临时文件 + `unzip -t` + `mv` 原子替换 + `trap` 清理。

- [ ] **Step 4: 跑测试，确认全部通过**

Run: `.venv/bin/python -m pytest tests/test_archive_repo_script.py -v`
Expected: 10 passed

- [ ] **Step 5: 跑仓库门禁**

Run: `make check`
Expected: 全绿

- [ ] **Step 6: 提交**

```bash
git add scripts/archive_repo.sh tests/test_archive_repo_script.py
git commit -m "archive_repo.sh 补齐 CLI 契约与原子替换：默认输出、参数/依赖/仓库检查、unzip -t 校验"
```

---

## Task 3: 真实仓库验收

无代码改动；只验证脚本对本仓库的实际产物。若验收发现问题，回 Task 1/2 修复后重跑。

- [ ] **Step 1: 在真实仓库运行（默认输出）**

Run: `scripts/archive_repo.sh`
Expected: 打印 `archive: <仓库根>/dist/langharness-main-<时间戳>.zip`、`entries: N files`、`size: X`

- [ ] **Step 2: 校验条目数与完整性**

Run: `unzip -t dist/langharness-main-*.zip && unzip -Z1 dist/langharness-main-*.zip | grep -v '/\.git/' | wc -l && git ls-files | wc -l`
Expected: `unzip -t` 无错误；两个计数相等（跟踪文件数 140）；`.git/` 条目存在

- [ ] **Step 3: 解压回验 git 可用性**

Run:
```bash
rm -rf /tmp/archive-check && mkdir -p /tmp/archive-check && unzip -q dist/langharness-main-*.zip -d /tmp/archive-check && git -C /tmp/archive-check/langharness-main log --oneline -3 && git -C /tmp/archive-check/langharness-main status --porcelain | head
```
Expected: `git log` 显示最近三条提交；`git status` 干净（当前工作区干净，打包的即工作区状态）

- [ ] **Step 4: 最终门禁**

Run: `make check`
Expected: 全绿

- [ ] **Step 5: 清理验收目录**

Run: `rm -rf /tmp/archive-check`
Expected: 无输出（`dist/` 里的 zip 保留，属被 .gitignore 忽略的正常产物）
