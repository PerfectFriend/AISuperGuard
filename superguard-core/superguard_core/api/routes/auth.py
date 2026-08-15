"""
SuperGuard Core - Auth API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superguard_core.core.auth import (
    Token, TokenData, UserCreate, UserUpdate, UserResponse,
    verify_password, get_password_hash, create_access_token, create_refresh_token,
    decode_token, get_current_user, require_role, get_user_sites
)
from superguard_core.core.database import get_session, User, UserRole
from superguard_core.core.events import publish_auth_event, get_event_bus

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    """Login with email and password."""
    result = await session.execute(
        select(User).where(User.email == form_data.username)
    )
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        await publish_auth_event(
            await get_event_bus(), "login_failed",
            {"email": form_data.username, "reason": "invalid_credentials"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )
    
    # Update last login
    user.last_login = datetime.now(timezone.utc)
    await session.commit()
    
    # Get user's sites
    site_ids = await get_user_sites(user, session)
    
    # Create tokens
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "site_ids": site_ids,
    }
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    await publish_auth_event(
        await get_event_bus(), "login_success",
        {"user_id": user.id, "email": user.email, "site_ids": site_ids}
    )
    
    settings = get_settings()
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str,
    session: AsyncSession = Depends(get_session),
):
    """Refresh access token using refresh token."""
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    
    user_id = payload.get("sub")
    result = await session.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    site_ids = await get_user_sites(user, session)
    
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "site_ids": site_ids,
    }
    
    access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)
    
    settings = get_settings()
    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get current user info."""
    site_ids = await get_user_sites(user, session)
    return UserResponse(
        id=user.id,
        uuid=user.uuid,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
        site_ids=site_ids,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """Create new user (admin only)."""
    # Check if email exists
    result = await session.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Validate site IDs
    if user_data.site_ids:
        from superguard_core.core.database import Site
        result = await session.execute(select(Site.id).where(Site.id.in_(user_data.site_ids)))
        valid_sites = [row[0] for row in result.all()]
        if len(valid_sites) != len(user_data.site_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more site IDs are invalid",
            )
    
    user = User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
    )
    session.add(user)
    await session.flush()
    
    # Assign sites
    if user_data.site_ids:
        from superguard_core.core.database import site_users
        for site_id in user_data.site_ids:
            await session.execute(
                site_users.insert().values(user_id=user.id, site_id=site_id, role=user_data.role)
            )
    
    await session.commit()
    await session.refresh(user)
    
    await publish_auth_event(
        await get_event_bus(), "user_created",
        {"user_id": user.id, "email": user.email, "role": user.role.value}
    )
    
    site_ids = await get_user_sites(user, session)
    return UserResponse(
        id=user.id,
        uuid=user.uuid,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
        site_ids=site_ids,
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """List all users (admin only)."""
    result = await session.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    
    response = []
    for user in users:
        site_ids = await get_user_sites(user, session)
        response.append(UserResponse(
            id=user.id,
            uuid=user.uuid,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            last_login=user.last_login,
            created_at=user.created_at,
            site_ids=site_ids,
        ))
    return response


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """Update user (admin only)."""
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if user_data.full_name is not None:
        user.full_name = user_data.full_name
    if user_data.role is not None:
        user.role = user_data.role
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    if user_data.site_ids is not None:
        from superguard_core.core.database import Site, site_users
        # Validate site IDs
        result = await session.execute(select(Site.id).where(Site.id.in_(user_data.site_ids)))
        valid_sites = [row[0] for row in result.all()]
        if len(valid_sites) != len(user_data.site_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more site IDs are invalid",
            )
        # Clear existing and add new
        await session.execute(site_users.delete().where(site_users.c.user_id == user_id))
        for site_id in user_data.site_ids:
            await session.execute(
                site_users.insert().values(user_id=user_id, site_id=site_id, role=user_data.role or user.role)
            )
    
    await session.commit()
    await session.refresh(user)
    
    await publish_auth_event(
        await get_event_bus(), "user_updated",
        {"user_id": user.id, "email": user.email}
    )
    
    site_ids = await get_user_sites(user, session)
    return UserResponse(
        id=user.id,
        uuid=user.uuid,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
        site_ids=site_ids,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """Delete user (admin only)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )
    
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    await session.delete(user)
    await session.commit()
    
    await publish_auth_event(
        await get_event_bus(), "user_deleted",
        {"user_id": user_id}
    )


from datetime import datetime, timezone