"""The handwriting model learned from your own writing, for the pens (web/pens.js, web/hwr-worker.js).

FineNotes' "Learn my handwriting" tunes Grape on lines you copied in its practice notebook and keeps the
result as one file (its personal.bin). With DAF_HWR_MODEL naming that file, Daf serves it at
/api/hwr/model and the worker reads with it first, falling back to Grape as shipped
(web/vendor/hwr/grape-2.0.bin) when there is none or it can't be read. The file is read each time,
since learning again replaces it; its ETag lets a device that already has it keep its copy.
"""
from pathlib import Path

from fastapi import HTTPException, Response
from fastapi.responses import FileResponse

from . import config


def model_path() -> Path | None:
    p = Path(config.HWR_MODEL) if config.HWR_MODEL else None
    return p if p and p.is_file() else None


def etag(p: Path) -> str:
    st = p.stat()
    return f'"{st.st_mtime_ns:x}-{st.st_size:x}"'


def response(if_none_match: str | None = None):
    p = model_path()
    if not p:
        raise HTTPException(404, "No learned handwriting model")
    tag = etag(p)
    headers = {"Cache-Control": "private, no-cache", "ETag": tag}
    if if_none_match and tag in (t.strip() for t in if_none_match.split(",")):
        return Response(status_code=304, headers=headers)
    return FileResponse(p, media_type="application/octet-stream", headers=headers)
