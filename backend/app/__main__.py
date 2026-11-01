import os
from pathlib import Path

import uvicorn

from .config import Settings
from .main import create_app


def _drop_privileges(data_dir: Path) -> None:
    """If started as root (the default in Docker/Unraid), make the data volume
    writable for PUID/PGID (default 10001) and run as that user.

    Unraid convention: PUID=99 PGID=100 (nobody:users).
    """
    if os.getuid() != 0:
        return
    uid = int(os.environ.get("PUID", 10001))
    gid = int(os.environ.get("PGID", 10001))
    data_dir.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(data_dir):
        for name in [".", *dirs, *files]:
            path = os.path.join(root, name)
            st = os.lstat(path)
            if st.st_uid != uid or st.st_gid != gid:
                os.lchown(path, uid, gid)
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)


if __name__ == "__main__":
    settings = Settings.from_env()
    config = uvicorn.Config(
        create_app(settings), host="0.0.0.0", port=settings.port, log_level="info"
    )
    config.load()  # import everything while still privileged
    _drop_privileges(settings.data_dir)
    uvicorn.Server(config).run()
