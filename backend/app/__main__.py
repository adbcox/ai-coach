import uvicorn

from .config import Settings
from .main import create_app

if __name__ == "__main__":
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port, log_level="info")
