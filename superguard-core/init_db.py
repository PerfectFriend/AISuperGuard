import asyncio
from superguard_core.core.database import init_db, get_session_factory, User, UserRole, Site
from superguard_core.core.auth import get_password_hash
from superguard_core.core.config import Settings
from sqlalchemy import select

async def init():
    settings = Settings()
    await init_db(settings.database_url)
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Check if we already have a superuser
        result = await session.execute(select(User).where(User.email == "admin@test.com"))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                email="admin@test.com",
                password_hash=get_password_hash("admin123"),
                full_name="Admin User",
                role=UserRole.ADMIN,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            print("Created admin user: admin@test.com / admin")
        else:
            print("Admin user already exists")

        # Create a test site
        result = await session.execute(select(Site).where(Site.name == "Test Site"))
        site = result.scalar_one_or_none()
        if not site:
            site = Site(
                name="Test Site",
                description="A test site for API testing",
                timezone="UTC",
                is_active=True,
            )
            session.add(site)
            await session.flush()
            print("Created test site: Test Site")
        else:
            print("Test site already exists")

        await session.commit()

if __name__ == "__main__":
    asyncio.run(init())
