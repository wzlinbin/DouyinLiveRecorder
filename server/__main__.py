from __future__ import annotations

import uvicorn

from .runtime_config import admin_host, admin_port


def main() -> None:
    uvicorn.run("server.app:app", host=admin_host(), port=admin_port(), reload=False)


if __name__ == "__main__":
    main()
