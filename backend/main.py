"""Serve the corridor atlas. Chat text is not on any route."""

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.atlas import location_document, map_document, service_status

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
app = FastAPI(title="PedalAtlas", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/status")
def status() -> dict:
    return service_status()


@app.get("/api/map")
def map_data() -> dict:
    return map_document()


@app.get("/api/locations/{location_id}")
def location(location_id: str) -> dict:
    document = location_document(location_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Unknown place")
    return document


def main() -> None:
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
