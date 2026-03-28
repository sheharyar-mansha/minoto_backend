from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from config.settings import UPLOAD_DIR, settings

MAX_BYTES = settings.MAX_VOICE_UPLOAD_MB * 1024 * 1024


def save_streaming_upload(upload: UploadFile, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds {settings.MAX_VOICE_UPLOAD_MB} MB",
                    )
                out.write(chunk)
    finally:
        upload.file.close()
    if total == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty file")


def remove_file_if_exists(relative_path: str | None) -> None:
    if not relative_path:
        return
    p = UPLOAD_DIR / relative_path
    if p.is_file():
        p.unlink()
