"""数据快照钉值（唯一事实源——本地与 CI 同读；CD 定期前移见 .github/workflows/data-cron.yml）.

设计：hsr-data update 的产物定期打包成 GitHub Release 资产（data-snapshot.tar.gz），
CI/本地只从镜像恢复数据环境——上游改名/改版/删库/网络抖动均不影响。
tag 语义 = data-full-<日期>（全量快照）。
"""

#: 全量数据快照镜像（首个为 2026-10-16 手工 bootstrap；之后 CD 每两周生产）
SNAPSHOT_REPO = "pzc2004/HSR_Nous"
SNAPSHOT_TAG = "data-full-20261016"
SNAPSHOT_ASSET = "data-snapshot.tar.gz"


def snapshot_url(tag: str | None = None) -> str:
    """数据快照 tar 包的永久下载地址（缺省=当前钉值）."""
    return (
        f"https://github.com/{SNAPSHOT_REPO}/releases/download/"
        f"{tag or SNAPSHOT_TAG}/{SNAPSHOT_ASSET}"
    )
