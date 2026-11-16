"""Run one persistent candidate task in a detached, controlled worker."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from hsr_nous.common import research_root
from hsr_nous.research.core.artifacts import ArtifactStore
from hsr_nous.research.core.tasks import CandidateTaskManager
from hsr_nous.research.schema import canonical_json


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id")
    parser.add_argument("--research-root", type=Path)
    args = parser.parse_args(argv)
    root = (args.research_root or research_root()).resolve()
    manager = CandidateTaskManager(ArtifactStore(root / "artifacts"))
    task = manager.run(args.task_id)
    print(canonical_json({
        "task_id": task["task_id"],
        "status": task["status"],
        "report_id": task["report_id"],
    }), flush=True)
    return 0 if task["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
