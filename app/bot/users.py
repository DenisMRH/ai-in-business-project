from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_or_create_user(session: AsyncSession, telegram_user_id: int) -> User:
    stmt = select(User).where(User.telegram_user_id == telegram_user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(telegram_user_id=telegram_user_id)
    session.add(user)
    await session.flush()
    return user
