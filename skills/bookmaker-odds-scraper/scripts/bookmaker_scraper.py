#!/usr/bin/env python3
"""Bookmaker Odds Scraper - Multi-strategy engine for extracting betting odds.

Supports API interception, DOM parsing, and WebSocket monitoring.
Designed for use without authentication.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "playwright",
#     "httpx",
#     "beautifulsoup4",
# ]
# ///

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import random
import re
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Ensure stdout can handle unicode/emoji on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class Selection:
    """A single selectable outcome within a market (e.g. '1' -> 'Juventus' @ 2.50)."""

    name: str    # "1", "X", "2", "OVER", "UNDER"
    label: str   # "Juventus", "Pareggio", "Over 2.5"
    odds: float  # 2.50


@dataclass
class Market:
    """A betting market with its selections (e.g. '1X2 Esito Finale')."""

    market_type: str          # "1X2", "OVER_UNDER", "DOUBLE_CHANCE"
    market_name: str          # "Esito Finale", "Under/Over 2.5"
    selections: list[Selection]


@dataclass
class Event:
    """A single sporting event with all scraped markets."""

    event_id: str
    home_team: str
    away_team: str
    start_time: str
    competition: str
    markets: list[Market]
    source_url: str = ""
    strategy_used: str = ""


@dataclass
class ScrapeResult:
    """Top-level result container for a scrape run."""

    scrape_timestamp: str
    bookmaker: str
    sport: str
    competition: str
    events: list[Event]
    errors: list[str]
    metadata: dict


# ---------------------------------------------------------------------------
# Browser Manager
# ---------------------------------------------------------------------------


class BrowserManager:
    """Manages Playwright Chromium browser lifecycle with stealth settings.

    Usage::

        async with BrowserManager(headless=True) as mgr:
            ctx = await mgr.new_context()
            page = await ctx.new_page()
            ...
    """

    _STEALTH_INIT = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['it-IT', 'it', 'en-US', 'en']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        window.chrome = {runtime: {}};
    """

    _USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._playwright: Any = None
        self._browser: Any = None

    async def __aenter__(self) -> "BrowserManager":
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def new_context(self) -> Any:
        """Create a new browser context with stealth init scripts."""
        ctx = await self._browser.new_context(
            user_agent=self._USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="it-IT",
            timezone_id="Europe/Rome",
        )
        await ctx.add_init_script(self._STEALTH_INIT)
        return ctx


# ---------------------------------------------------------------------------
# API Interceptor
# ---------------------------------------------------------------------------


class ApiInterceptor:
    """Attaches to a Playwright page and captures JSON API responses.

    In *discover* mode every request is recorded.  In *scrape* mode only
    responses whose URL matches one of the configured glob patterns are kept.
    """

    def __init__(self, url_patterns: list[str] | None = None) -> None:
        self.url_patterns = url_patterns or []
        self.captured_responses: list[dict] = []
        self.all_requests: list[dict] = []
        self._regexes = [self._glob_to_regex(p) for p in self.url_patterns]

    @staticmethod
    def _glob_to_regex(glob: str) -> re.Pattern[str]:
        """Convert a simple glob pattern to a compiled regex."""
        escaped = re.escape(glob)
        escaped = escaped.replace(r"\*\*", ".*")
        escaped = escaped.replace(r"\*", "[^/]*")
        escaped = escaped.replace(r"\?", ".")
        return re.compile(escaped)

    def _matches(self, url: str) -> bool:
        if not self._regexes:
            return True  # discover mode – match everything
        return any(rx.search(url) for rx in self._regexes)

    async def _handle_response(self, response: Any) -> None:
        """Handler attached via ``page.on('response', ...)``."""
        url = response.url
        status = response.status
        content_type = response.headers.get("content-type", "")

        self.all_requests.append(
            {"url": url, "status": status, "content_type": content_type}
        )

        if not self._matches(url):
            return

        if "json" not in content_type and "javascript" not in content_type:
            return

        try:
            body = await response.json()
            self.captured_responses.append(
                {"url": url, "status": status, "body": body}
            )
        except Exception:
            pass  # non-JSON body or decoding error – skip silently

    def setup(self, page: Any) -> None:
        """Attach the interceptor to *page*."""
        page.on("response", self._handle_response)


# ---------------------------------------------------------------------------
# WebSocket Monitor
# ---------------------------------------------------------------------------


class WebSocketMonitor:
    """Captures WebSocket connection info and messages from a Playwright page."""

    _MAX_MSG_LEN = 2000

    def __init__(self) -> None:
        self.connections: list[dict] = []
        self.messages: list[dict] = []

    def setup(self, page: Any) -> None:
        """Attach the monitor to *page*."""
        page.on("websocket", self._handle_ws)

    def _handle_ws(self, ws: Any) -> None:
        ws_url = ws.url
        self.connections.append({"url": ws_url, "opened_at": _now_iso()})

        def on_frame(payload: Any) -> None:
            text = str(payload)
            if len(text) > self._MAX_MSG_LEN:
                text = text[: self._MAX_MSG_LEN] + "…[truncated]"
            self.messages.append({"ws_url": ws_url, "data": text, "ts": _now_iso()})

        ws.on("framereceived", on_frame)
        ws.on("framesent", on_frame)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATIC_EXTS = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".ico", ".map",
}

_HOME_KEYS = [
    "home", "homeTeam", "home_team", "team1",
    "squadra1", "casa", "homeTeamName", "homeName",
]
_AWAY_KEYS = [
    "away", "awayTeam", "away_team", "team2",
    "squadra2", "trasferta", "awayTeamName", "awayName",
]
_EVENT_LIST_KEYS = [
    "events", "matches", "partite", "risultati",
    "data", "items", "content", "results", "competitions",
    "meetings", "fixtures",
]

COOKIE_SELECTORS = [
    "button:has-text('Accetta')",
    "button:has-text('Accept')",
    "button:has-text('Accetto')",
    "button:has-text('Accetta tutti')",
    "#onetrust-accept-btn-handler",
    ".cookie-accept",
    "[data-testid='cookie-accept']",
    "button[id*='cookie']",
    "button[id*='consent']",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _random_delay(lo: float = 0.3, hi: float = 1.2) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


def _safe_float(val: Any) -> float:
    """Try hard to coerce *val* to a float, return 0.0 on failure."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Base Adapter (ABC)
# ---------------------------------------------------------------------------


class BaseAdapter(ABC):
    """Abstract base for all bookmaker adapters.

    Subclasses may override the ``parse_*`` family of methods to handle
    site-specific response formats.  The default implementations use
    heuristic / generic parsing.
    """

    def __init__(self, config: dict, bookmaker_key: str) -> None:
        self.config = config
        self.bookmaker_key = bookmaker_key
        self.strategies: list[str] = config.get("strategies", ["api", "dom"])

    # -- URL helpers --------------------------------------------------------

    def get_url(self, sport: str, competition: str | None = None) -> str:
        """Build the target URL from the config path templates."""
        base = self.config.get("base_url", "")
        sport_paths: dict = self.config.get("sport_paths", {})
        sport_path = sport_paths.get(sport, "")
        url = f"{base}{sport_path}"
        if competition:
            comp_paths: dict = self.config.get("competition_paths", {})
            comp_path = comp_paths.get(competition, f"/{competition}")
            url = f"{url}{comp_path}"
        return url

    # -- Main entry ---------------------------------------------------------

    async def scrape(
        self, browser_mgr: BrowserManager, sport: str, competition: str | None = None
    ) -> ScrapeResult:
        """Run scrape strategies in order, returning the first successful result."""
        url = self.get_url(sport, competition)
        all_events: list[Event] = []
        errors: list[str] = []
        strategy_used = ""

        for strategy in self.strategies:
            try:
                print(f"  🔍 Trying strategy '{strategy}' for {self.bookmaker_key}…")
                if strategy in ("api", "api_intercept"):
                    events = await self._scrape_via_api(browser_mgr, url)
                elif strategy in ("dom", "dom_parse"):
                    events = await self._scrape_via_dom(browser_mgr, url)
                elif strategy == "websocket":
                    events = await self._scrape_via_websocket(browser_mgr, url)
                else:
                    errors.append(f"Unknown strategy: {strategy}")
                    continue

                if events:
                    all_events = events
                    strategy_used = strategy
                    print(f"  ✓ Strategy '{strategy}' returned {len(events)} event(s)")
                    break
                else:
                    msg = f"Strategy '{strategy}' returned 0 events"
                    errors.append(msg)
                    print(f"  ⚠ {msg}")
            except Exception as exc:
                msg = f"Strategy '{strategy}' failed: {exc}"
                errors.append(msg)
                print(f"  ✗ {msg}")

        for ev in all_events:
            ev.source_url = url
            ev.strategy_used = strategy_used

        return ScrapeResult(
            scrape_timestamp=_now_iso(),
            bookmaker=self.bookmaker_key,
            sport=sport,
            competition=competition or "",
            events=all_events,
            errors=errors,
            metadata={"url": url, "strategy_used": strategy_used},
        )

    # -- Strategy implementations -------------------------------------------

    async def _scrape_via_api(
        self, browser_mgr: BrowserManager, url: str
    ) -> list[Event]:
        """Navigate to *url*, intercept XHR/Fetch JSON and parse events."""
        patterns = self.config.get("api_patterns", [])
        interceptor = ApiInterceptor(patterns)

        ctx = await browser_mgr.new_context()
        try:
            page = await ctx.new_page()
            interceptor.setup(page)
            await self._navigate_with_delays(page, url)
            await self._interact_for_data(page)
            await _random_delay(1.0, 2.5)

            events: list[Event] = []
            for resp in interceptor.captured_responses:
                events.extend(self.parse_api_response(resp["body"], resp["url"]))
            return events
        finally:
            await ctx.close()

    async def _scrape_via_dom(
        self, browser_mgr: BrowserManager, url: str
    ) -> list[Event]:
        """Navigate to *url*, wait for render, then parse the DOM."""
        ctx = await browser_mgr.new_context()
        try:
            page = await ctx.new_page()
            await self._navigate_with_delays(page, url)
            await self._interact_for_data(page)
            await _random_delay(1.0, 2.0)
            html = await page.content()
            return self.parse_html(html, url)
        finally:
            await ctx.close()

    async def _scrape_via_websocket(
        self, browser_mgr: BrowserManager, url: str
    ) -> list[Event]:
        """Navigate to *url*, monitor WebSocket traffic and parse events."""
        ws_monitor = WebSocketMonitor()
        ctx = await browser_mgr.new_context()
        try:
            page = await ctx.new_page()
            ws_monitor.setup(page)
            await self._navigate_with_delays(page, url)
            await self._interact_for_data(page)
            # Give WS some time to receive data
            await asyncio.sleep(random.uniform(3.0, 5.0))

            events: list[Event] = []
            for msg in ws_monitor.messages:
                try:
                    data = json.loads(msg["data"])
                    events.extend(self.parse_ws_message(data))
                except (json.JSONDecodeError, TypeError):
                    pass
            return events
        finally:
            await ctx.close()

    # -- Navigation helpers -------------------------------------------------

    async def _navigate_with_delays(self, page: Any, url: str) -> None:
        """Navigate to *url*, dismiss cookie banners, and wait for content.

        Uses 'networkidle' wait, configurable delays from anti_bot config,
        and exponential backoff retry on transient failures.
        """
        # Read per-bookmaker anti-bot config
        ab = self.config.get("anti_bot", {})
        wait_ms = ab.get("wait_before_scrape_ms", 8000)
        delay_lo, delay_hi = ab.get("random_delay_range_ms", [2000, 5000])
        wait_s = wait_ms / 1000.0
        delay_lo_s = delay_lo / 1000.0
        delay_hi_s = delay_hi / 1000.0

        for attempt in range(3):
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
                break
            except Exception as exc:
                print(f"  ⚠ Navigation attempt {attempt+1} failed: {exc}")
                if attempt < 2:
                    backoff = 2 ** attempt
                    print(f"     Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                else:
                    print(f"  ✗ Navigation failed after 3 attempts")
                    return

        # Wait for JS to settle (configurable per bookmaker)
        await asyncio.sleep(wait_s)

        # Dismiss cookie banners
        for selector in COOKIE_SELECTORS:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    await btn.click(timeout=3000)
                    await asyncio.sleep(random.uniform(delay_lo_s * 0.3, delay_hi_s * 0.3))
                    break
            except Exception:
                continue

        # Anti-bot wait after cookie banner
        await asyncio.sleep(random.uniform(delay_lo_s, delay_hi_s))

    async def _interact_for_data(self, page: Any) -> None:
        """Scroll, click accordions, and trigger lazy-loaded content."""
        ab = self.config.get("anti_bot", {})
        delay_lo, delay_hi = ab.get("random_delay_range_ms", [2000, 5000])
        delay_lo_s = delay_lo / 1000.0
        delay_hi_s = delay_hi / 1000.0

        # Scroll down multiple times to trigger lazy load
        for i in range(6):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            await asyncio.sleep(random.uniform(delay_lo_s * 0.4, delay_hi_s * 0.4))

            # Click any "Load more" / "Mostra altro" buttons
            load_more_selectors = [
                "button:has-text('Mostra')",
                "button:has-text('Load')",
                "button:has-text('Altro')",
                "[class*='load-more']",
                "[class*='show-more']",
                "[class*='altro']",
            ]
            for sel in load_more_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=500):
                        await btn.click(timeout=2000)
                        await asyncio.sleep(random.uniform(delay_lo_s * 0.5, delay_hi_s * 0.5))
                except Exception:
                    pass

        # Scroll back up
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(random.uniform(delay_lo_s * 0.3, delay_hi_s * 0.3))

        # Wait for network to settle after all interactions
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # Extra configurable settle time
        settle_ms = ab.get("extra_settle_ms", 3000)
        await asyncio.sleep(settle_ms / 1000.0)

    # -- Parsing (overridable) ----------------------------------------------

    def parse_api_response(self, data: Any, url: str) -> list[Event]:
        """Parse a JSON API response into events. Override for site-specific logic."""
        return self._generic_json_parse(data, url)

    def parse_html(self, html: str, url: str) -> list[Event]:
        """Parse rendered HTML into events. Override for site-specific logic."""
        return self._generic_html_parse(html, url)

    def parse_ws_message(self, data: Any) -> list[Event]:
        """Parse a WebSocket JSON frame into events. Override for site-specific logic."""
        if isinstance(data, dict):
            return self._generic_json_parse(data, "ws")
        return []

    # -- Generic JSON parsing -----------------------------------------------

    def _generic_json_parse(self, data: Any, url: str) -> list[Event]:
        """Recursively walk *data* looking for event-like objects."""
        events: list[Event] = []
        self._walk_json(data, url, events, depth=0)
        return events

    def _walk_json(
        self, node: Any, url: str, acc: list[Event], depth: int
    ) -> None:
        if depth > 15:
            return
        if isinstance(node, dict):
            ev = self._try_parse_event_from_dict(node, url)
            if ev:
                acc.append(ev)
                return  # don't recurse into an already-parsed event
            for key in _EVENT_LIST_KEYS:
                if key in node and isinstance(node[key], (list, dict)):
                    self._walk_json(node[key], url, acc, depth + 1)
                    return
            # Fallback – recurse all values
            for v in node.values():
                if isinstance(v, (dict, list)):
                    self._walk_json(v, url, acc, depth + 1)
        elif isinstance(node, list):
            for item in node:
                self._walk_json(item, url, acc, depth + 1)

    def _try_parse_event_from_dict(self, d: dict, url: str) -> Event | None:
        """Extract an event from *d* by checking common key names."""
        home = self._find_first(d, _HOME_KEYS)
        away = self._find_first(d, _AWAY_KEYS)
        if not home or not away:
            return None

        event_id = str(
            d.get("id", d.get("eventId", d.get("event_id", d.get("matchId", ""))))
        )
        start_time = str(
            d.get(
                "startTime",
                d.get(
                    "start_time",
                    d.get("date", d.get("dataOra", d.get("kickoff", ""))),
                ),
            )
        )
        competition = str(
            d.get(
                "competition",
                d.get(
                    "league",
                    d.get("competizione", d.get("tournament", "")),
                ),
            )
        )
        markets = self._extract_markets_from_dict(d)
        return Event(
            event_id=event_id,
            home_team=str(home),
            away_team=str(away),
            start_time=start_time,
            competition=competition,
            markets=markets,
            source_url=url,
        )

    @staticmethod
    def _find_first(d: dict, keys: list[str]) -> Any:
        for k in keys:
            if k in d:
                return d[k]
        return None

    def _extract_markets_from_dict(self, d: dict) -> list[Market]:
        """Extract odds/markets from a dict using common structures."""
        markets: list[Market] = []
        # Look for top-level odds keys (1X2 shorthand)
        odds_1 = _safe_float(d.get("odds1", d.get("quota1", d.get("odd1"))))
        odds_x = _safe_float(d.get("oddsX", d.get("quotaX", d.get("oddX"))))
        odds_2 = _safe_float(d.get("odds2", d.get("quota2", d.get("odd2"))))
        if odds_1 and odds_x and odds_2:
            markets.append(
                Market(
                    market_type="1X2",
                    market_name="Esito Finale",
                    selections=[
                        Selection("1", d.get("home", d.get("homeTeam", "1")), odds_1),
                        Selection("X", "Pareggio", odds_x),
                        Selection("2", d.get("away", d.get("awayTeam", "2")), odds_2),
                    ],
                )
            )

        # Look for a nested 'markets' / 'odds' / 'mercati' list
        for mk in ("markets", "odds", "mercati", "bets", "scommesse"):
            mkt_data = d.get(mk)
            if isinstance(mkt_data, list):
                for m in mkt_data:
                    if not isinstance(m, dict):
                        continue
                    mtype = str(m.get("type", m.get("marketType", "")))
                    mname = str(m.get("name", m.get("marketName", mtype)))
                    sels: list[Selection] = []
                    outcomes = m.get("outcomes", m.get("selections", m.get("esiti", [])))
                    if isinstance(outcomes, list):
                        for o in outcomes:
                            if isinstance(o, dict):
                                sels.append(
                                    Selection(
                                        name=str(o.get("name", o.get("label", ""))),
                                        label=str(o.get("label", o.get("name", ""))),
                                        odds=_safe_float(
                                            o.get("odds", o.get("quota", o.get("price")))
                                        ),
                                    )
                                )
                    if sels:
                        markets.append(Market(market_type=mtype, market_name=mname, selections=sels))
                break  # only first matching key
            elif isinstance(mkt_data, dict):
                for mkey, mval in mkt_data.items():
                    if isinstance(mval, dict):
                        sels = []
                        for sk, sv in mval.items():
                            odds_val = _safe_float(sv)
                            if odds_val > 1.0:
                                sels.append(Selection(name=sk, label=sk, odds=odds_val))
                        if sels:
                            markets.append(Market(market_type=mkey, market_name=mkey, selections=sels))
                break

        return markets

    # -- Generic HTML parsing -----------------------------------------------

    def _generic_html_parse(self, html: str, url: str) -> list[Event]:
        """Use CSS selectors from config (or sensible defaults) to find events."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        selectors = self.config.get("selectors", {})
        event_sel = selectors.get(
            "event_row",
            ".event-row, .match-row, tr.event, [data-type='event'], .rj-ev-list__ev-card",
        )

        rows = soup.select(event_sel)
        events: list[Event] = []
        for row in rows:
            ev = self._parse_event_row(row, url)
            if ev:
                events.append(ev)
        return events

    def _parse_event_row(self, row: Any, url: str) -> Event | None:
        """Parse a single event row from HTML."""
        selectors = self.config.get("selectors", {})

        home_sel = selectors.get("home_team", ".home-team, .team-home, .team1")
        away_sel = selectors.get("away_team", ".away-team, .team-away, .team2")
        odds_sel = selectors.get("odds", ".odds-value, .quota, .odd, [data-odd]")

        home_el = row.select_one(home_sel)
        away_el = row.select_one(away_sel)
        if not home_el or not away_el:
            return None

        home = home_el.get_text(strip=True)
        away = away_el.get_text(strip=True)
        if not home or not away:
            return None

        odds_els = row.select(odds_sel)
        selections: list[Selection] = []
        labels = ["1", "X", "2"]
        for i, el in enumerate(odds_els):
            val = _safe_float(el.get_text(strip=True).replace(",", "."))
            if val > 1.0:
                name = labels[i] if i < len(labels) else str(i)
                selections.append(Selection(name=name, label=name, odds=val))

        markets: list[Market] = []
        if selections:
            markets.append(
                Market(market_type="1X2", market_name="Esito Finale", selections=selections)
            )

        return Event(
            event_id="",
            home_team=home,
            away_team=away,
            start_time="",
            competition="",
            markets=markets,
            source_url=url,
        )

    # -- Discovery mode -----------------------------------------------------

    async def discover(
        self, browser_mgr: BrowserManager, sport: str
    ) -> dict:
        """Capture ALL network traffic for discovery / reverse-engineering."""
        url = self.get_url(sport)
        interceptor = ApiInterceptor([])  # no filter – capture everything
        ws_monitor = WebSocketMonitor()

        ctx = await browser_mgr.new_context()
        try:
            page = await ctx.new_page()
            interceptor.setup(page)
            ws_monitor.setup(page)
            await self._navigate_with_delays(page, url)
            await self._interact_for_data(page)
            await asyncio.sleep(random.uniform(3.0, 5.0))

            # Filter static assets
            api_requests = [
                r for r in interceptor.all_requests
                if not any(r["url"].lower().endswith(ext) for ext in _STATIC_EXTS)
            ]

            return {
                "bookmaker": self.bookmaker_key,
                "url": url,
                "discovered_at": _now_iso(),
                "total_requests": len(interceptor.all_requests),
                "filtered_requests": len(api_requests),
                "api_requests": api_requests[:200],  # cap output size
                "json_responses": [
                    {"url": r["url"], "status": r["status"], "body_preview": _truncate(r["body"])}
                    for r in interceptor.captured_responses[:50]
                ],
                "websocket_connections": ws_monitor.connections,
                "websocket_messages": ws_monitor.messages[:100],
            }
        finally:
            await ctx.close()


def _truncate(obj: Any, max_len: int = 3000) -> Any:
    """Truncate a JSON-serialisable object for previewing."""
    text = json.dumps(obj, default=str, ensure_ascii=False)
    if len(text) > max_len:
        return json.loads(text[:max_len] + '"')  # best effort
    return obj


# ---------------------------------------------------------------------------
# Concrete Adapters & Registry
# ---------------------------------------------------------------------------

ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {}


def register_adapter(key: str):
    """Decorator to register a bookmaker adapter class."""

    def decorator(cls: type[BaseAdapter]) -> type[BaseAdapter]:
        ADAPTER_REGISTRY[key] = cls
        return cls

    return decorator


def get_adapter(key: str, config: dict) -> BaseAdapter:
    """Factory: return a registered adapter or fall back to GenericAdapter."""
    bk_config = config.get(key, {})
    cls = ADAPTER_REGISTRY.get(key, GenericAdapter)
    return cls(bk_config, key)


# -- GenericAdapter ---------------------------------------------------------


class GenericAdapter(BaseAdapter):
    """Concrete adapter that works purely from config.  No overrides needed."""
    pass


# -- Site-specific adapters (v1 – thin wrappers) ----------------------------


@register_adapter("snai")
class SnaiAdapter(GenericAdapter):
    """Adapter for SNAI.it"""
    pass


@register_adapter("eurobet")
class EurobetAdapter(GenericAdapter):
    """Adapter for Eurobet.it"""
    pass


@register_adapter("goldbet")
class GoldbetAdapter(GenericAdapter):
    """Adapter for Goldbet.it"""
    pass


@register_adapter("williamhill")
class WilliamHillAdapter(GenericAdapter):
    """Adapter for WilliamHill.it"""
    pass


@register_adapter("sisal")
class SisalAdapter(GenericAdapter):
    """Adapter for Sisal.it"""
    pass


@register_adapter("lottomatica")
class LottomaticaAdapter(GenericAdapter):
    """Adapter for Lottomatica.it (Better)"""
    pass


@register_adapter("bet365")
class Bet365Adapter(GenericAdapter):
    """Adapter for Bet365.it"""
    pass


@register_adapter("oddsportal")
class OddsPortalAdapter(BaseAdapter):
    """Adapter for OddsPortal.com – an odds aggregator.

    This adapter provides a specialised ``parse_html`` that handles the
    multi-bookmaker comparison table format.  Each event's markets may
    contain odds tagged with the originating bookmaker name.
    """

    def parse_html(self, html: str, url: str) -> list[Event]:
        """Parse the OddsPortal multi-bookmaker HTML table."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        events: list[Event] = []

        # OddsPortal uses dynamic class names – try common patterns
        event_rows = soup.select(
            "div.eventRow, div[class*='eventRow'], tr.deactivate, "
            "div[class*='match-row'], div[data-testid='event-row']"
        )

        for row in event_rows:
            # Extract teams
            teams = row.select("a[class*='team'], span[class*='team'], .participant-name")
            if len(teams) < 2:
                name_el = row.select_one("a[href*='/match/'], a[class*='name']")
                if name_el:
                    parts = name_el.get_text(strip=True).split(" - ")
                    if len(parts) == 2:
                        home, away = parts[0].strip(), parts[1].strip()
                    else:
                        continue
                else:
                    continue
            else:
                home = teams[0].get_text(strip=True)
                away = teams[1].get_text(strip=True)

            # Extract odds cells
            odds_cells = row.select(
                "div[class*='odds'], td.odds-cell, span[class*='odds-value']"
            )
            selections: list[Selection] = []
            labels = ["1", "X", "2"]
            for i, cell in enumerate(odds_cells):
                val = _safe_float(cell.get_text(strip=True).replace(",", "."))
                if val > 1.0:
                    # Try to get bookmaker tooltip/title
                    bk_name = cell.get("title", cell.get("data-bookmaker", ""))
                    label = labels[i] if i < len(labels) else str(i)
                    if bk_name:
                        label = f"{label} ({bk_name})"
                    selections.append(Selection(name=labels[i] if i < len(labels) else str(i), label=label, odds=val))

            markets: list[Market] = []
            if selections:
                markets.append(
                    Market(
                        market_type="1X2",
                        market_name="Esito Finale (aggregator: OddsPortal)",
                        selections=selections,
                    )
                )

            events.append(
                Event(
                    event_id="",
                    home_team=home,
                    away_team=away,
                    start_time="",
                    competition="",
                    markets=markets,
                    source_url=url,
                    strategy_used="dom",
                )
            )

        return events

    def parse_api_response(self, data: Any, url: str) -> list[Event]:
        """Parse OddsPortal JSON API (v2 feeds)."""
        events = self._generic_json_parse(data, url)
        # Tag every event coming from OddsPortal as aggregator data
        for ev in events:
            for mkt in ev.markets:
                if "aggregator" not in mkt.market_name.lower():
                    mkt.market_name = f"{mkt.market_name} (aggregator: OddsPortal)"
        return events


# ---------------------------------------------------------------------------
# Config Loader
# ---------------------------------------------------------------------------


def load_config() -> dict:
    """Load ``bookmakers.json`` from the same directory as this script."""
    config_path = Path(__file__).parent / "bookmakers.json"
    if not config_path.exists():
        print(f"  ⚠ Config file not found: {config_path}")
        return {}
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_meta", None)  # strip metadata key
    return data


# ---------------------------------------------------------------------------
# Output Writer
# ---------------------------------------------------------------------------


def write_output(data: Any, output_path: str) -> None:
    """Write *data* as indented JSON to *output_path*.

    Handles dataclass serialisation via ``dataclasses.asdict``.
    """

    def _serialise(obj: Any) -> Any:
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=_serialise, ensure_ascii=False)

    print(f"  ✓ Output written to {path}")


# ---------------------------------------------------------------------------
# CLI Subcommands
# ---------------------------------------------------------------------------


async def cmd_scrape(args: argparse.Namespace, config: dict) -> None:
    """Scrape a specific bookmaker for odds."""
    bookmaker = args.bookmaker
    sport = args.sport
    competition = getattr(args, "competition", None)
    headless = args.headless

    print(f"📊 Scraping {bookmaker} | sport={sport} | competition={competition or 'all'}")

    adapter = get_adapter(bookmaker, config)

    async with BrowserManager(headless=headless) as mgr:
        result = adapter_result = await adapter.scrape(mgr, sport, competition)

    if result.events:
        print(f"  ✓ Found {len(result.events)} event(s)")
    else:
        print(f"  ⚠ No events found")

    write_output(result, args.output)


async def cmd_list_bookmakers(args: argparse.Namespace, config: dict) -> None:
    """List all configured bookmakers with their status."""
    info = []
    for key, cfg in config.items():
        if not isinstance(cfg, dict):
            continue
        info.append(
            {
                "key": key,
                "name": cfg.get("name", key),
                "enabled": cfg.get("enabled", True),
                "base_url": cfg.get("base_url", ""),
                "strategies": cfg.get("strategies", []),
                "sports": list(cfg.get("sport_paths", {}).keys()),
                "competitions": list(cfg.get("competition_paths", {}).keys()),
                "has_custom_adapter": key in ADAPTER_REGISTRY,
            }
        )

    if not info:
        print("  ⚠ No bookmakers configured in bookmakers.json")
    else:
        print(f"  📊 {len(info)} bookmaker(s) configured")
        for bk in info:
            status = "✓ enabled" if bk["enabled"] else "✗ disabled"
            print(f"    {status}  {bk['key']:20s} {bk['name']}")

    write_output(info, args.output)


async def cmd_discover(args: argparse.Namespace, config: dict) -> None:
    """Discovery mode: capture ALL network traffic from a bookmaker."""
    bookmaker = args.bookmaker
    sport = args.sport
    headless = args.headless

    print(f"🔍 Discovery mode for {bookmaker} | sport={sport}")

    adapter = get_adapter(bookmaker, config)

    async with BrowserManager(headless=headless) as mgr:
        report = await adapter.discover(mgr, sport)

    print(f"  📊 Captured {report['filtered_requests']} request(s), "
          f"{len(report['json_responses'])} JSON response(s), "
          f"{len(report['websocket_connections'])} WS connection(s)")

    write_output(report, args.output)


async def cmd_compare(args: argparse.Namespace, config: dict) -> None:
    """Scrape multiple bookmakers and output combined results."""
    bookmaker_keys = [b.strip() for b in args.bookmakers.split(",")]
    sport = args.sport
    competition = getattr(args, "competition", None)
    headless = args.headless

    print(f"📊 Comparing {len(bookmaker_keys)} bookmaker(s) | sport={sport}")

    results: list[ScrapeResult] = []

    async with BrowserManager(headless=headless) as mgr:
        for key in bookmaker_keys:
            print(f"\n── {key} ─────────────────────────────")
            adapter = get_adapter(key, config)
            try:
                result = await adapter.scrape(mgr, sport, competition)
                results.append(result)
                print(f"  ✓ {len(result.events)} event(s) from {key}")
            except Exception as exc:
                print(f"  ✗ Failed to scrape {key}: {exc}")
                results.append(
                    ScrapeResult(
                        scrape_timestamp=_now_iso(),
                        bookmaker=key,
                        sport=sport,
                        competition=competition or "",
                        events=[],
                        errors=[str(exc)],
                        metadata={},
                    )
                )
            # Polite delay between bookmakers
            await _random_delay(1.5, 3.0)

    total_events = sum(len(r.events) for r in results)
    print(f"\n📊 Total: {total_events} event(s) across {len(results)} bookmaker(s)")

    write_output(results, args.output)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate async subcommand."""
    parser = argparse.ArgumentParser(
        prog="bookmaker_scraper",
        description="Bookmaker Odds Scraper - Multi-strategy engine for extracting betting odds.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # -- scrape -------------------------------------------------------------
    sp_scrape = subparsers.add_parser("scrape", help="Scrape a specific bookmaker for odds")
    sp_scrape.add_argument("--bookmaker", required=True, help="Bookmaker key (e.g. snai, eurobet)")
    sp_scrape.add_argument("--sport", default="calcio", help="Sport to scrape (default: calcio)")
    sp_scrape.add_argument("--competition", default=None, help="Competition slug")
    sp_scrape.add_argument("--output", required=True, help="Output JSON file path")
    sp_scrape.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    sp_scrape.add_argument("--no-headless", dest="headless", action="store_false", help="Show browser window")
    sp_scrape.set_defaults(func=cmd_scrape)

    # -- list-bookmakers ----------------------------------------------------
    sp_list = subparsers.add_parser("list-bookmakers", help="List all configured bookmakers")
    sp_list.add_argument("--output", required=True, help="Output JSON file path")
    sp_list.set_defaults(func=cmd_list_bookmakers)

    # -- discover -----------------------------------------------------------
    sp_disc = subparsers.add_parser("discover", help="Discover network endpoints for a bookmaker")
    sp_disc.add_argument("--bookmaker", required=True, help="Bookmaker key")
    sp_disc.add_argument("--sport", default="calcio", help="Sport (default: calcio)")
    sp_disc.add_argument("--output", required=True, help="Output JSON file path")
    sp_disc.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    sp_disc.add_argument("--no-headless", dest="headless", action="store_false", help="Show browser window")
    sp_disc.set_defaults(func=cmd_discover)

    # -- compare ------------------------------------------------------------
    sp_comp = subparsers.add_parser("compare", help="Compare odds across multiple bookmakers")
    sp_comp.add_argument("--bookmakers", required=True, help="Comma-separated bookmaker keys")
    sp_comp.add_argument("--sport", default="calcio", help="Sport (default: calcio)")
    sp_comp.add_argument("--competition", default=None, help="Competition slug")
    sp_comp.add_argument("--output", required=True, help="Output JSON file path")
    sp_comp.add_argument("--headless", action="store_true", default=True, help="Run headless (default)")
    sp_comp.add_argument("--no-headless", dest="headless", action="store_false", help="Show browser window")
    sp_comp.set_defaults(func=cmd_compare)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    asyncio.run(args.func(args, load_config()))


if __name__ == "__main__":
    main()
