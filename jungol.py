"""JUNGOL profile scraping and per-guild registration storage (no Discord dependency)."""

import html
import re
import sqlite3
import time

import aiohttp


BASE_URL = "https://jungol.co.kr"
USER_AGENT = "Mozilla/5.0 (compatible; YupiBot)"
CACHE_SECONDS = 300
MAX_CONCURRENT_REQUESTS = 5

_TITLE = re.compile(r"<title>@(.+?) - JUNGOL</title>")
_RATING = re.compile(r"AC 레이팅</dt>\s*<dd[^>]*>(?:<!--.*?-->)*\s*([0-9,]+)점", re.S)
_TIER = re.compile(r'<meta property="og:description" content="([A-Za-z]+(?: [IVX]+)?) ')
_RANK = re.compile(r'<meta property="og:description" content="[^"]*? rank ([0-9,]+)')
_JOINED = re.compile(r'<meta property="og:description" content="[^"]*? joined ([0-9/]+)')
_NEXT_TIER = re.compile(r"다음 티어까지 AC 레이팅 ([0-9,]+) 필요")
_PROBLEM_TITLE = re.compile(r'<meta property="og:title" content="([^"]*)"')
_PROBLEM_STATS = re.compile(r'<meta property="og:description" content="[^"]*?([0-9,]+) solved users[^"]*?([0-9,]+) submissions')


def new_session() -> aiohttp.ClientSession:
    # JUNGOL answers with a Link preload header larger than aiohttp's 8 KB default.
    return aiohttp.ClientSession(max_field_size=65536)


class JungolError(Exception):
    """User-facing lookup failure."""


class Profile:
    def __init__(self, account_id: int, nickname: str, rating: int, tier: str,
                 rank: int | None = None, joined: str = "", next_tier_points: int | None = None):
        self.account_id = account_id
        self.nickname = nickname
        self.rating = rating
        self.tier = tier
        self.rank = rank
        self.joined = joined
        self.next_tier_points = next_tier_points


class Problem:
    def __init__(self, number: int, title: str, tier: str, solved_users: int, submissions: int):
        self.number = number
        self.title = title
        self.tier = tier
        self.solved_users = solved_users
        self.submissions = submissions

    @property
    def url(self) -> str:
        return f"{BASE_URL}/problem/{self.number}"

    @property
    def image_url(self) -> str:
        return f"{BASE_URL}/og/problem/{self.number}.png"


def account_path(text: str) -> str:
    """Map a numeric id or a (@)nickname to the /account/ URL path segment."""
    text = text.strip()
    if re.fullmatch(r"[0-9]+", text):
        return text
    nickname = text.lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", nickname):
        raise JungolError("정올 ID는 숫자 ID 또는 닉네임(@닉네임)으로 입력해 주세요.")
    return "@" + nickname


def parse_profile(page: str, account_id: int) -> Profile:
    title, rating = _TITLE.search(page), _RATING.search(page)
    if not title or not rating:
        raise JungolError("정올 프로필에서 AC 레이팅을 찾지 못했어요.")
    tier, rank, joined, next_tier = _TIER.search(page), _RANK.search(page), _JOINED.search(page), _NEXT_TIER.search(page)
    return Profile(account_id, html.unescape(title.group(1)), _to_int(rating.group(1)),
                   tier.group(1) if tier else "",
                   _to_int(rank.group(1)) if rank else None,
                   joined.group(1) if joined else "",
                   _to_int(next_tier.group(1)) if next_tier else None)


def format_joined(joined: str) -> str:
    """Turn JUNGOL's M/D/YYYY into YYYY-MM-DD."""
    try:
        month, day, year = map(int, joined.split("/"))
    except ValueError:
        return joined
    return f"{year:04d}-{month:02d}-{day:02d}"


def _to_int(text: str) -> int:
    return int(text.replace(",", ""))


def parse_problem(page: str, number: int) -> Problem:
    title, stats = _PROBLEM_TITLE.search(page), _PROBLEM_STATS.search(page)
    if not title or not stats:
        raise JungolError("정올 문제 정보를 찾지 못했어요.")
    name, _, tier = html.unescape(title.group(1)).rpartition(" · ")
    return Problem(number, name or tier, tier if name else "", _to_int(stats.group(1)), _to_int(stats.group(2)))


async def _fetch_page(session: aiohttp.ClientSession, path: str, not_found: str) -> tuple[str, str]:
    """Return (final URL path, HTML) for a JUNGOL page."""
    try:
        async with session.get(f"{BASE_URL}/{path}", headers={"User-Agent": USER_AGENT},
                               timeout=aiohttp.ClientTimeout(total=15)) as response:
            if response.status == 404:
                raise JungolError(not_found)
            if response.status != 200:
                raise JungolError(f"정올에서 응답을 받지 못했어요. (HTTP {response.status})")
            return response.url.path, await response.text()
    except (aiohttp.ClientError, TimeoutError):
        raise JungolError("정올에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.") from None


async def fetch_profile(session: aiohttp.ClientSession, text: str) -> Profile:
    final_path, page = await _fetch_page(session, f"account/{account_path(text)}", "해당 정올 계정을 찾을 수 없어요.")
    try:
        account_id = int(final_path.rsplit("/", 1)[-1])
    except ValueError:
        raise JungolError("정올에서 계정 정보를 확인하지 못했어요.") from None
    return parse_profile(page, account_id)


async def fetch_problem(session: aiohttp.ClientSession, number: int) -> Problem:
    _, page = await _fetch_page(session, f"problem/{number}", "해당 정올 문제를 찾을 수 없어요.")
    return parse_problem(page, number)


class ProfileCache:
    def __init__(self, ttl: float = CACHE_SECONDS):
        self.ttl = ttl
        self._entries: dict[int, tuple[float, Profile]] = {}

    def get(self, account_id: int, now: float | None = None) -> Profile | None:
        entry = self._entries.get(account_id)
        now = time.time() if now is None else now
        if entry and now - entry[0] < self.ttl:
            return entry[1]
        return None

    def put(self, profile: Profile, now: float | None = None):
        self._entries[profile.account_id] = (time.time() if now is None else now, profile)


class JungolStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def init_db(self):
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS jungol_users (
                guild_id INTEGER NOT NULL,
                discord_user_id INTEGER NOT NULL,
                jungol_account_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, discord_user_id)
            )
        """)
        self.connection.commit()

    def register(self, guild_id: int, discord_user_id: int, jungol_account_id: int):
        self.connection.execute(
            "INSERT OR REPLACE INTO jungol_users VALUES (?, ?, ?)",
            (guild_id, discord_user_id, jungol_account_id),
        )
        self.connection.commit()

    def account_id(self, guild_id: int, discord_user_id: int) -> int | None:
        row = self.connection.execute(
            "SELECT jungol_account_id FROM jungol_users WHERE guild_id = ? AND discord_user_id = ?",
            (guild_id, discord_user_id),
        ).fetchone()
        return row[0] if row else None

    def members(self, guild_id: int) -> list[tuple[int, int]]:
        """Return (discord_user_id, jungol_account_id) pairs registered in a guild."""
        return self.connection.execute(
            "SELECT discord_user_id, jungol_account_id FROM jungol_users WHERE guild_id = ?",
            (guild_id,),
        ).fetchall()
