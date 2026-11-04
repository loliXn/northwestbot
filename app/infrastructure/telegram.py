"""How the bot reaches the Telegram Bot API: directly, through a proxy, or via another Bot API server."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import ClientDecodeError, TelegramNetworkError, TelegramUnauthorizedError
from aiogram.methods import TelegramMethod
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError

from app.core.config import Settings

logger = logging.getLogger("telegram")

# Short enough that a blocked server fails the 20-second deployment check
# instead of looking healthy while it waits.
STARTUP_CHECK_TIMEOUT = 10
UNREACHABLE_HINT = (
    "If this server's network blocks Telegram, run the bot on a server in another "
    "country, or set TELEGRAM_PROXY or TELEGRAM_API_URL in .env."
)


# aiohttp-socks raises its own errors, which aiogram passes through untouched.
PROXY_ERRORS = (ProxyError, ProxyConnectionError, ProxyTimeoutError)


class TelegramSession(AiohttpSession):
    """Reports a failing proxy as TelegramNetworkError, like any other network failure.

    Code that already retries or reports network errors (the reminder sender,
    the startup check) then covers proxy trouble too.
    """

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:
        try:
            return await super().make_request(bot, method, timeout)
        except PROXY_ERRORS as exc:
            raise TelegramNetworkError(method=method, message=f"Proxy error: {exc}") from exc


def build_session(settings: Settings) -> TelegramSession:
    session = TelegramSession(proxy=settings.telegram_proxy)
    if settings.telegram_api_url:
        session.api = TelegramAPIServer.from_base(settings.telegram_api_url)
    return session


def _endpoint(url: str) -> str:
    """scheme://host[:port] of a URL, without credentials or path."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    return f"{parts.scheme}://{host}" + (f":{port}" if port else "")


def describe_route(settings: Settings) -> str:
    """Where Telegram requests go, safe to log: never the proxy password or a relay's secret path."""
    server = _endpoint(settings.telegram_api_url) if settings.telegram_api_url else "api.telegram.org"
    if settings.telegram_proxy:
        return f"{server} through proxy {_endpoint(settings.telegram_proxy)}"
    return server


async def check_connection(bot: Bot, settings: Settings) -> bool:
    """Reach Telegram once before starting, and explain a failure in one log line."""
    route = describe_route(settings)
    try:
        me = await bot.get_me(request_timeout=STARTUP_CHECK_TIMEOUT)
    except TelegramUnauthorizedError:
        logger.error("Telegram rejected BOT_TOKEN. Copy the token from @BotFather into .env again.")
        return False
    except TelegramNetworkError as exc:
        logger.error("Cannot reach Telegram at %s (%s). %s", route, exc.message, UNREACHABLE_HINT)
        return False
    except ClientDecodeError:
        # Typically a network's block page, or a TELEGRAM_API_URL that is not a Bot API server.
        logger.error("%s answered with something other than the Telegram Bot API. %s", route, UNREACHABLE_HINT)
        return False
    logger.info("Connected to Telegram as @%s via %s", me.username, route)
    return True
