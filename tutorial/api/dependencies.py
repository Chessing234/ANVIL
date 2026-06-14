"""FastAPI dependencies: database sessions, coordinator, bus, and demo auth."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings, get_settings
from core.message_bus import MessageBus
from orchestration.coordinator import TutorialCoordinator

from api.schemas import User


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a transactional async session bound to the app database manager."""
    db_manager = request.app.state.db_manager
    async with db_manager.session() as session:
        yield session


def get_coordinator(request: Request) -> TutorialCoordinator:
    """Return the process-wide ``TutorialCoordinator`` instance."""
    return request.app.state.coordinator


def get_message_bus(request: Request) -> MessageBus:
    """Return the async message bus singleton."""
    return request.app.state.message_bus


def get_app_settings() -> Settings:
    """Cached application settings."""
    return get_settings()


async def get_current_user(
    request: Request,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_app_settings),
) -> User:
    """Validate the demo API key header."""
    expected = settings.api.demo_api_key
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )
    return User(api_key_id="demo")


DbSession = Annotated[AsyncSession, Depends(get_db)]
CoordinatorDep = Annotated[TutorialCoordinator, Depends(get_coordinator)]
MessageBusDep = Annotated[MessageBus, Depends(get_message_bus)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
CurrentUser = Annotated[User, Depends(get_current_user)]
