"""Serve the corridor atlas. Chat text is not on any route."""

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.atlas import location_document, map_document, service_status
from backend.guide import answer
from backend.stages import route_bundle
from backend.wiki import article_or_none, public_index

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


class GuideRequest(BaseModel):
    message: str = Field(max_length=500)


@app.get("/api/route")
def route(start: str, end: str) -> dict:
    bundle = route_bundle(start, end)
    if bundle is None:
        raise HTTPException(status_code=404, detail="No schematic path")
    return bundle


@app.get("/api/wiki")
def wiki_index() -> dict:
    return {"articles": public_index(), "credibility": "published_orientation"}


@app.get("/api/wiki/{article_id}")
def wiki_article(article_id: str) -> dict:
    article = article_or_none(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="No published page")
    return article


@app.post("/api/guide")
def guide(request: GuideRequest) -> dict:
    return answer(request.message)


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
