#!/bin/bash
# 清扫 hsr-sim web 孤儿服务器（ppid=1 为根的 uv/hsr-sim 进程树，整树 TERM→KILL）。
#
# 历史（2026-09-07）：一次性 `bash -c 'uv run hsr-sim web … &'` 起的 dev 服务器
# 全部孤儿化，单机清出 159 个拖垮负载。此后新起的服务器自带孤儿看护（属主死亡
# 即自停，--no-orphan-guard 可关），本脚本只用于清扫看护上线前的存量/漏网。
set -euo pipefail

python3 - <<'EOF'
import os, re, signal, subprocess, time

def alive(p: int) -> bool:
    try:
        os.kill(p, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

out = subprocess.check_output(['ps', '-axo', 'pid,ppid,command']).decode()
procs = {}
for line in out.splitlines()[1:]:
    parts = line.split(None, 2)
    if len(parts) < 3:
        continue
    pid, ppid, cmd = parts
    procs[int(pid)] = (int(ppid), cmd)

pat = re.compile(r'hsr-sim|HSR_Nous|uv run')
cand = {pid for pid, (_, cmd) in procs.items() if pat.search(cmd)}

children = {}
for pid, (ppid, _) in procs.items():
    children.setdefault(ppid, []).append(pid)

# 以 ppid=1 的本项目进程为根，向下收集整棵树
kill_set = set()
for r in [pid for pid in cand if procs[pid][0] == 1]:
    stack = [r]
    while stack:
        p = stack.pop()
        if p in kill_set:
            continue
        kill_set.add(p)
        stack.extend(children.get(p, []))

if not kill_set:
    print('没有 hsr-sim/uv 孤儿进程。')
    raise SystemExit(0)

print(f'发现 {len(kill_set)} 个孤儿进程，TERM…')
for p in kill_set:
    try:
        os.kill(p, signal.SIGTERM)
    except ProcessLookupError:
        pass
time.sleep(3)

left = [p for p in kill_set if alive(p)]
if left:
    print(f'{len(left)} 个未退，补 KILL')
    for p in left:
        try:
            os.kill(p, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(1)
    left = [p for p in left if alive(p)]

print(f'清理完成，存活 {len(left)} / {len(kill_set)}')
EOF
