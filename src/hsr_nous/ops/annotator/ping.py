"""`annotator.sh ping` 后端：LLM API 连通性自检（换 API 后第一件事）."""

from __future__ import annotations

from hsr_nous.ops.annotator.llm import ping


def main() -> int:
    try:
        print(ping())
        return 0
    except Exception as e:  # noqa: BLE001 —— 配置/传输错误原样给出（key 永不出现在错误里）
        print(f"ping FAIL：{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
