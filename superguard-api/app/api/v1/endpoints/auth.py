"""
Auth endpoints - login, register (invite only), refresh, me, admin: invite tokens, audit logs
"""
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.models import User, RefreshToken, AuditLog, InviteToken, UserRole, SiteUser
from app.schemas import (
    TokenResponse,
    LoginRequest,
    RegisterRequest,
    RefreshRequest,
    UserResponse,
)
from app.core.config import settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("uid")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def require_admin_with_db(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require user to have admin role in at least one site or be superuser.
    Use this inside route functions where db is available.
    """
    if user.is_superuser:
        return user
    from app.models import SiteUser
    result = await db.execute(
        select(SiteUser).where(SiteUser.user_id == user.id, SiteUser.role == UserRole.ADMIN)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


async def log_audit(
    db: AsyncSession,
    user_id: Optional[str],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: dict = None,
    request: Request = None,
):
    """Log an audit event."""
    ip = request.client.host if request and request.client else None
    ua = request.headers.get("user-agent") if request else None
    audit = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip,
        user_agent=ua,
    )
    db.add(audit)
    await db.flush()


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Try username first, then email
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user and req.username.find('@') != -1:
        result = await db.execute(select(User).where(User.email == req.username))
        user = result.scalar_one_or_none()
    
    if not user or not verify_password(req.password, user.hashed_password):
        await log_audit(db, None, "login_failed", "user", None, {"username": req.username}, request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    user.last_login = datetime.utcnow()

    # Get user roles from site_users
    from app.models import SiteUser
    roles_result = await db.execute(select(SiteUser.role).where(SiteUser.user_id == user.id))
    roles = [r.value for r in roles_result.scalars().all()]
    if user.is_superuser:
        roles.append("admin")

    token = create_access_token(subject=user.username, user_id=str(user.id), roles=roles)
    refresh = create_refresh_token(user_id=str(user.id))

    # Save refresh token hash
    from hashlib import sha256
    rt = RefreshToken(
        user_id=user.id,
        token_hash=sha256(refresh.encode()).hexdigest(),
        expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(rt)
    await db.flush()

    await log_audit(db, user.id, "login", "user", user.id, {"username": user.username}, request)
    
    return TokenResponse(access_token=token, refresh_token=refresh)


@router.post("/register", response_model=UserResponse)
async def register(req: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Validate invite token
    if not req.invite_token:
        await log_audit(db, None, "register_failed", "user", None, {"reason": "missing_invite_token"}, request)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token required")
    
    result = await db.execute(select(InviteToken).where(InviteToken.token == req.invite_token))
    invite = result.scalar_one_or_none()
    if not invite:
        await log_audit(db, None, "register_failed", "user", None, {"reason": "invalid_invite_token"}, request)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite token")
    
    if invite.expires_at and invite.expires_at.replace(tzinfo=None) < datetime.utcnow():
        await log_audit(db, None, "register_failed", "user", None, {"reason": "expired_invite_token"}, request)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token expired")
    
    if invite.used_count >= invite.max_uses:
        await log_audit(db, None, "register_failed", "user", None, {"reason": "invite_token_exhausted"}, request)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite token exhausted")
    
    # Check username/email uniqueness
    existing = await db.execute(select(User).where(User.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered")
    
    if req.email:
        existing = await db.execute(select(User).where(User.email == req.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=get_password_hash(req.password),
        full_name=req.full_name,
    )
    db.add(user)
    await db.flush()
    
    # Assign site role from invite
    if invite.site_id:
        site_user = SiteUser(
            site_id=invite.site_id,
            user_id=user.id,
            role=invite.role,
        )
        db.add(site_user)
    
    # Increment invite usage
    invite.used_count += 1
    
    await log_audit(db, user.id, "register", "user", user.id, {"username": user.username, "invite_token": req.invite_token}, request)
    
    return user


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("uid")
    from hashlib import sha256
    token_hash = sha256(req.refresh_token.encode()).hexdigest()

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
    )
    rt = result.scalar_one_or_none()
    if not rt:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    from app.models import SiteUser
    roles_result = await db.execute(select(SiteUser.role).where(SiteUser.user_id == user.id))
    roles = [r.value for r in roles_result.scalars().all()]
    if user.is_superuser:
        roles.append("admin")

    new_access = create_access_token(subject=user.username, user_id=str(user.id), roles=roles)
    new_refresh = create_refresh_token(user_id=str(user.id))
    rt.revoked_at = datetime.utcnow()

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


# Admin endpoints

class InviteTokenCreate(BaseModel):
    site_id: Optional[str] = None
    role: UserRole = UserRole.VIEWER
    max_uses: int = 1
    expires_days: Optional[int] = None


class InviteTokenResponse(BaseModel):
    id: str
    token: str
    site_id: Optional[str]
    role: UserRole
    max_uses: int
    used_count: int
    expires_at: Optional[datetime]
    created_at: datetime
    created_by: str

    class Config:
        from_attributes = True


@router.post("/admin/invites", response_model=InviteTokenResponse)
async def create_invite_token(
    req: InviteTokenCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new invite token (admin only)."""
    # Check admin permissions
    await require_admin_with_db(user, db)
    token = secrets.token_urlsafe(32)
    expires_at = None
    if req.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=req.expires_days)
    
    invite = InviteToken(
        token=token,
        created_by=user.id,
        site_id=req.site_id,
        role=req.role,
        max_uses=req.max_uses,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.flush()
    
    await log_audit(db, user.id, "invite_create", "invite_token", invite.id, {
        "token": token[:8] + "...",
        "site_id": req.site_id,
        "role": req.role.value,
        "max_uses": req.max_uses,
        "expires_days": req.expires_days,
    }, request)
    
    return invite


@router.get("/admin/invites", response_model=List[InviteTokenResponse])
async def list_invite_tokens(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all invite tokens (admin only)."""
    await require_admin_with_db(user, db)
    result = await db.execute(select(InviteToken).order_by(desc(InviteToken.created_at)))
    return result.scalars().all()


@router.delete("/admin/invites/{invite_id}")
async def revoke_invite_token(
    invite_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an invite token (admin only)."""
    await require_admin_with_db(user, db)
    result = await db.execute(select(InviteToken).where(InviteToken.id == invite_id))
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite token not found")
    
    await log_audit(db, user.id, "invite_revoke", "invite_token", invite_id, {
        "token": invite.token[:8] + "...",
    }, request)
    
    await db.delete(invite)
    await db.flush()
    return {"status": "revoked"}


class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str]
    site_id: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: dict
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/admin/audit", response_model=List[AuditLogResponse])
async def list_audit_logs(
    limit: int = 100,
    offset: int = 0,
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    site_id: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List audit logs (admin only)."""
    await require_admin_with_db(user, db)
    from sqlalchemy import and_
    
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if user_id:
        conditions.append(AuditLog.user_id == user_id)
    if site_id:
        conditions.append(AuditLog.site_id == site_id)
    
    query = select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit).offset(offset)
    if conditions:
        query = query.where(and_(*conditions))
    
    result = await db.execute(query)
    return result.scalars().all()