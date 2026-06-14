"""启动 FastAPI 应用。"""

from __future__ import annotations

import os
import sys

import uvicorn


def main() -> None:
    """使用当前解释器直接启动 API 服务。"""

    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("PORT", "8000"))
    uvicorn.run("api.main:app", host="127.0.0.1", port=port, reload=True)


if __name__ == "__main__":
    main()
