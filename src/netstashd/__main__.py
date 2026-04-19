"""Entry point for running the server with `python -m stashd`."""

import uvicorn

from netstashd.config import settings


def main() -> None:
    uvicorn.run(
        "netstashd.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
