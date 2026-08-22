"""
Notifiers endpoints - CRUD, test
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Notifier, User
from app.api.v1.endpoints.auth import get_current_user
from app.schemas import NotifierCreate, NotifierResponse
from app.services.telegram_bot import get_telegram_bot

router = APIRouter()


@router.get("/sites/{site_id}/notifiers", response_model=List[NotifierResponse])
async def list_notifiers(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notifier).where(Notifier.site_id == site_id).order_by(Notifier.created_at)
    )
    return result.scalars().all()


@router.post("/sites/{site_id}/notifiers", response_model=NotifierResponse, status_code=201)
async def create_notifier(
    site_id: str,
    req: NotifierCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    n = Notifier(site_id=site_id, **req.model_dump())
    db.add(n)
    await db.flush()
    return n


@router.delete("/sites/{site_id}/notifiers/{notifier_id}", status_code=204)
async def delete_notifier(
    site_id: str,
    notifier_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notifier).where(Notifier.id == notifier_id, Notifier.site_id == site_id)
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Notifier not found")
    await db.delete(n)
    await db.flush()


@router.post("/sites/{site_id}/notifiers/{notifier_id}/test")
async def test_notifier(
    site_id: str,
    notifier_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notifier).where(Notifier.id == notifier_id, Notifier.site_id == site_id)
    )
    n = result.scalar_one_or_none()
    if not n:
        raise HTTPException(status_code=404, detail="Notifier not found")
    
    # Actually test the notifier
    if n.type.value == "telegram":
        bot = await get_telegram_bot()
        if bot and bot.application:
            try:
                config = n.config or {}
                chat_id = config.get("chat_id")
                if chat_id:
                    await bot.application.bot.send_message(
                        chat_id=int(chat_id),
                        text=f"🧪 <b>Test Notification</b>\n\nNotifier: <b>{n.name}</b>\nType: Telegram\nStatus: ✅ Working",
                        parse_mode="HTML"
                    )
                    return {"status": "ok", "message": "Test notification sent to Telegram"}
                else:
                    return {"status": "error", "message": "Chat ID not configured in notifier"}
            except Exception as e:
                return {"status": "error", "message": f"Failed to send: {str(e)}"}
        else:
            return {"status": "error", "message": "Telegram bot not initialized"}
    
    # For other types, return placeholder for now
    return {"status": "ok", "message": f"Test notification sent (placeholder for {n.type.value})"}