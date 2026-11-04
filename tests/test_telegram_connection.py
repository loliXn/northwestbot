"""Proxy and Bot API server settings, and the startup reachability check. Offline: nothing is sent."""

import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.exceptions import ClientDecodeError, TelegramNetworkError, TelegramUnauthorizedError
from aiogram.methods import GetMe
from aiogram.types import User

from app.core.config import Settings, parse_telegram_api_url, parse_telegram_proxy
from app.infrastructure.telegram import build_session, check_connection, describe_route


def _settings(**overrides) -> Settings:
    values = dict(
        bot_token="123:abc",
        database_path=Path("data/app.db"),
        reminder_check_interval=60,
        target_currency="RUB",
        currency_rounding="precise",
        base_reminder_time="16:00",
        base_timezone="Europe/Moscow",
        admin_ids=(),
    )
    values.update(overrides)
    return Settings(**values)


class ProxySettingTests(unittest.TestCase):
    def test_empty_means_direct(self):
        self.assertIsNone(parse_telegram_proxy(None))
        self.assertIsNone(parse_telegram_proxy("  "))

    def test_supported_schemes_are_kept_as_given(self):
        for url in (
            "socks5://127.0.0.1:1080",
            "socks4://proxy.example:1080",
            "http://proxy.example:3128",
            "socks5://user:p%40ss@proxy.example:1080",
        ):
            with self.subTest(url=url):
                self.assertEqual(parse_telegram_proxy(f" {url} "), url)

    def test_unsupported_scheme_is_rejected_without_echoing_the_value(self):
        with self.assertRaises(RuntimeError) as caught:
            parse_telegram_proxy("https://user:secret@proxy.example:443")
        self.assertNotIn("secret", str(caught.exception))

    def test_host_and_port_are_required(self):
        for url in ("socks5://proxy.example", "socks5://:1080", "socks5://proxy.example:notaport"):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                parse_telegram_proxy(url)


class ApiUrlSettingTests(unittest.TestCase):
    def test_empty_means_official_server(self):
        self.assertIsNone(parse_telegram_api_url(""))

    def test_trailing_slash_is_dropped(self):
        self.assertEqual(parse_telegram_api_url("https://botapi.example.com/relay/"), "https://botapi.example.com/relay")

    def test_non_http_urls_are_rejected(self):
        for url in ("botapi.example.com", "ftp://botapi.example.com", "https://"):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                parse_telegram_api_url(url)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_session_uses_the_official_server(self):
        session = build_session(_settings())
        try:
            self.assertIsNone(session.proxy)
            self.assertEqual(session.api.api_url("T", "getMe"), "https://api.telegram.org/botT/getMe")
        finally:
            await session.close()

    async def test_proxy_and_api_url_are_applied(self):
        from aiohttp_socks import ProxyConnector

        session = build_session(
            _settings(
                telegram_proxy="socks5://user:secret@proxy.example:1080",
                telegram_api_url="https://botapi.example.com/relay",
            )
        )
        try:
            self.assertEqual(session.proxy, "socks5://user:secret@proxy.example:1080")
            self.assertIs(session._connector_type, ProxyConnector)
            self.assertTrue(session._connector_init["rdns"])
            self.assertEqual(session.api.api_url("T", "getMe"), "https://botapi.example.com/relay/botT/getMe")
        finally:
            await session.close()


class ProxyErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_unreachable_proxy_is_a_telegram_network_error(self):
        # Port 9 (discard) is closed here, so the proxy connection is refused at once.
        session = build_session(_settings(telegram_proxy="socks5://user:secret@127.0.0.1:9"))
        bot = Bot(token="123456:fake", session=session)
        try:
            with self.assertRaises(TelegramNetworkError) as caught:
                await bot.get_me(request_timeout=5)
        finally:
            await session.close()
        self.assertIn("Proxy error", caught.exception.message)
        self.assertNotIn("secret", caught.exception.message)


class RouteDescriptionTests(unittest.TestCase):
    def test_direct(self):
        self.assertEqual(describe_route(_settings()), "api.telegram.org")

    def test_credentials_and_relay_paths_stay_out_of_logs(self):
        route = describe_route(
            _settings(
                telegram_proxy="socks5://user:secret@proxy.example:1080",
                telegram_api_url="https://relay.example.com/secret-path",
            )
        )
        self.assertEqual(route, "https://relay.example.com through proxy socks5://proxy.example:1080")


class StartupCheckTests(unittest.IsolatedAsyncioTestCase):
    def _bot(self, **get_me) -> AsyncMock:
        bot = AsyncMock()
        bot.get_me = AsyncMock(**get_me)
        return bot

    async def test_reachable_telegram_passes(self):
        bot = self._bot(return_value=User(id=1, is_bot=True, first_name="Bot", username="example_bot"))
        with self.assertLogs("telegram", "INFO") as logs:
            self.assertTrue(await check_connection(bot, _settings()))
        self.assertIn("Connected to Telegram as @example_bot via api.telegram.org", logs.output[0])
        self.assertEqual(bot.get_me.await_args.kwargs, {"request_timeout": 10})

    async def test_network_failure_explains_the_blocked_server_case(self):
        settings = _settings(telegram_proxy="socks5://user:secret@proxy.example:1080")
        bot = self._bot(side_effect=TelegramNetworkError(method=GetMe(), message="Request timeout error"))
        with self.assertLogs("telegram", "ERROR") as logs:
            self.assertFalse(await check_connection(bot, settings))
        message = logs.output[0]
        self.assertIn("Cannot reach Telegram at api.telegram.org through proxy socks5://proxy.example:1080", message)
        self.assertIn("Request timeout error", message)
        self.assertIn("TELEGRAM_PROXY", message)
        self.assertNotIn("secret", message)

    async def test_block_page_instead_of_the_api_is_explained(self):
        error = ClientDecodeError("Failed to deserialize object", ValueError("not JSON"), "<html>Blocked</html>")
        bot = self._bot(side_effect=error)
        with self.assertLogs("telegram", "ERROR") as logs:
            self.assertFalse(await check_connection(bot, _settings()))
        self.assertIn("api.telegram.org answered with something other than the Telegram Bot API", logs.output[0])

    async def test_rejected_token_is_named(self):
        bot = self._bot(side_effect=TelegramUnauthorizedError(method=GetMe(), message="Unauthorized"))
        with self.assertLogs("telegram", "ERROR") as logs:
            self.assertFalse(await check_connection(bot, _settings()))
        self.assertIn("Telegram rejected BOT_TOKEN", logs.output[0])


if __name__ == "__main__":
    unittest.main()
