"""
SuperGuard Core - Media API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from superguard_core.core.auth import get_current_user, verify_site_access
from superguard_core.core.database import get_session, AlarmMedia, MediaType, Alarm, Camera
from superguard_core.core.config import get_settings

router = APIRouter()


@router.get("/alarm/{alarm_id}")
async def get_alarm_media(
    site_id: int,
    alarm_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get all media for an alarm."""
    await verify_site_access(site_id, current_user, session)
    
    # Verify alarm exists and belongs to site
    result = await session.execute(
        select(Alarm).where(Alarm.id == alarm_id, Alarm.site_id == site_id)
    )
    alarm = result.scalar_one_or_none()
    
    if not alarm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alarm not found",
        )
    
    result = await session.execute(
        select(AlarmMedia)
        .where(AlarmMedia.alarm_id == alarm_id)
        .order_by(AlarmMedia.timestamp.desc())
    )
    media = result.scalars().all()
    
    return [
        {
            "id": m.id,
            "uuid": m.uuid,
            "type": m.type.value,
            "path": m.path,
            "thumbnail_path": m.thumbnail_path,
            "timestamp": m.timestamp.isoformat(),
            "file_size": m.file_size,
            "duration": m.duration,
            "metadata": m.metadata,
            "download_url": f"/media/download/{m.id}",
        }
        for m in media
    ]


@router.get("/camera/{camera_id}")
async def get_camera_media(
    site_id: int,
    camera_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    media_type: Optional[str] = Query(None),
):
    """Get media for a specific camera (continuous recordings + alarm media)."""
    await verify_site_access(site_id, current_user, session)
    
    # Verify camera exists
    result = await session.execute(
        select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )
    
    # Get alarm media for this camera
    query = select(AlarmMedia).where(AlarmMedia.camera_id == camera_id)
    
    if media_type:
        try:
            query = query.where(AlarmMedia.type == MediaType(media_type))
        except:
            pass
    
    query = query.order_by(AlarmMedia.timestamp.desc()).limit(limit).offset(offset)
    result = await session.execute(query)
    media = result.scalars().all()
    
    # Also get continuous recording segments (alarm_id = 0)
    continuous_query = select(AlarmMedia).where(
        AlarmMedia.camera_id == camera_id,
        AlarmMedia.alarm_id == 0
    ).order_by(AlarmMedia.timestamp.desc()).limit(limit).offset(offset)
    result = await session.execute(continuous_query)
    continuous = result.scalars().all()
    
    all_media = list(media) + list(continuous)
    all_media.sort(key=lambda m: m.timestamp, reverse=True)
    all_media = all_media[:limit]
    
    return [
        {
            "id": m.id,
            "uuid": m.uuid,
            "type": m.type.value,
            "alarm_id": m.alarm_id,
            "path": m.path,
            "thumbnail_path": m.thumbnail_path,
            "timestamp": m.timestamp.isoformat(),
            "file_size": m.file_size,
            "duration": m.duration,
            "metadata": m.metadata,
            "download_url": f"/media/download/{m.id}",
        }
        for m in all_media
    ]


@router.get("/download/{media_id}")
async def download_media(
    site_id: int,
    media_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Download media file."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(AlarmMedia)
        .join(Alarm, AlarmMedia.alarm_id == Alarm.id, isouter=True)
        .where(AlarmMedia.id == media_id)
    )
    media = result.scalar_one_or_none()
    
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )
    
    # Verify site access via alarm or camera
    if media.alarm_id > 0:
        alarm_result = await session.execute(
            select(Alarm).where(Alarm.id == media.alarm_id)
        )
        alarm = alarm_result.scalar_one_or_none()
        if alarm and alarm.site_id != site_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    else:
        camera_result = await session.execute(
            select(Camera).where(Camera.id == media.camera_id)
        )
        camera = camera_result.scalar_one_or_none()
        if camera and camera.site_id != site_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    
    file_path = Path(media.path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )
    
    # Determine media type for proper headers
    media_type_map = {
        MediaType.VIDEO: "video/mp4",
        MediaType.FRAME: "image/jpeg",
        MediaType.SNAPSHOT: "image/jpeg",
    }
    
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type=media_type_map.get(media.type, "application/octet-stream"),
    )


@router.get("/stream/{media_id}")
async def stream_media(
    site_id: int,
    media_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Stream video media (supports range requests for seeking)."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(AlarmMedia).where(AlarmMedia.id == media_id)
    )
    media = result.scalar_one_or_none()
    
    if not media or media.type != MediaType.VIDEO:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video not found",
        )
    
    file_path = Path(media.path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )
    
    # Support range requests for video seeking
    from fastapi import Request
    
    async def file_iterator(file_path: Path, start: int = 0, end: int = None):
        chunk_size = 1024 * 1024  # 1MB chunks
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = end - start if end else None
            while True:
                if remaining is not None and remaining <= 0:
                    break
                read_size = min(chunk_size, remaining) if remaining else chunk_size
                chunk = f.read(read_size)
                if not chunk:
                    break
                yield chunk
    
    file_size = file_path.stat().st_size
    
    # For now, return full file (range support can be added)
    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


@router.get("/thumbnail/{media_id}")
async def get_thumbnail(
    site_id: int,
    media_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thumbnail for media."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(AlarmMedia).where(AlarmMedia.id == media_id)
    )
    media = result.scalar_one_or_none()
    
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )
    
    # Try thumbnail first, then original for images
    thumb_path = media.thumbnail_path or media.path
    file_path = Path(thumb_path)
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail not found",
        )
    
    return FileResponse(
        path=file_path,
        media_type="image/jpeg",
    )


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    site_id: int,
    media_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete media file."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(AlarmMedia).where(AlarmMedia.id == media_id)
    )
    media = result.scalar_one_or_none()
    
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )
    
    # Verify site access
    if media.alarm_id > 0:
        alarm_result = await session.execute(
            select(Alarm).where(Alarm.id == media.alarm_id)
        )
        alarm = alarm_result.scalar_one_or_none()
        if alarm and alarm.site_id != site_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    
    # Delete file from disk
    try:
        file_path = Path(media.path)
        if file_path.exists():
            file_path.unlink()
        if media.thumbnail_path:
            thumb_path = Path(media.thumbnail_path)
            if thumb_path.exists():
                thumb_path.unlink()
    except Exception:
        pass  # Log but continue
    
    # Delete from database
    await session.delete(media)
    await session.commit()


from typing import Optional