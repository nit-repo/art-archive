"""python -m app  → starts the server at http://localhost:8000"""

import uvicorn

from . import config

if __name__ == "__main__":
    print(f"gamevid running at http://localhost:{config.PORT}  (Ctrl+C to stop)")
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, log_level="warning")
