"""Reminder time parsing and persistent storage (no Discord dependency)."""

import re
import sqlite3
from datetime import datetime, timedelta, timezone


KST = timezone(timedelta(hours=9), name="KST")
TIME_HELP = '시간은 "+2d 1h 30m" 또는 "261031 20:21" 형식으로 입력해 주세요. (한국 시간)'
MAX_MESSAGE_LENGTH = 1900


def parse_reminder_time(text: str, now: datetime | None = None) -> datetime:
    """Return an aware KST datetime; YY always means 2000 through 2099."""
    now = now if now is not None else datetime.now(KST)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(KST)
    text = text.strip()

    try:
        if text.startswith("+"):
            duration = text[1:].strip()
            # Accept spaced or compact units, but reject missing/duplicate units
            # and arbitrary text instead of silently ignoring it.
            if not re.fullmatch(r"(?:[0-9]+[dhm]\s*)+", duration):
                raise ValueError(TIME_HELP)
            parts = re.findall(r"([0-9]+)([dhm])", duration)
            if len({unit for _, unit in parts}) != len(parts):
                raise ValueError("d, h, m은 각각 한 번만 입력해 주세요.")
            seconds = sum(int(value) * {"d": 86400, "h": 3600, "m": 60}[unit]
                          for value, unit in parts)
            target = now + timedelta(seconds=seconds)
        else:
            match = re.fullmatch(r"([0-9]{2})([0-9]{2})([0-9]{2})\s+([0-9]{2}):([0-9]{2})", text)
            if not match:
                raise ValueError(TIME_HELP)
            year, month, day, hour, minute = map(int, match.groups())
            target = datetime(2000 + year, month, day, hour, minute, tzinfo=KST)
    except OverflowError:
        raise ValueError("예약 가능한 시간 범위를 벗어났어요.") from None
    except ValueError as exc:
        if str(exc) in (TIME_HELP, "d, h, m은 각각 한 번만 입력해 주세요."):
            raise
        raise ValueError("날짜와 시간을 확인해 주세요. " + TIME_HELP) from None

    if target <= now:
        raise ValueError("현재보다 미래의 시간을 입력해 주세요.")
    return target


class ReminderStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def init_db(self):
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                due_at REAL NOT NULL,
                next_attempt_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        self.connection.execute("""
            CREATE INDEX IF NOT EXISTS reminders_pending_due
            ON reminders (status, next_attempt_at)
        """)
        self.connection.commit()

    def add(self, user_id: int, channel_id: int, message: str, due_at: datetime) -> int:
        message = message.strip()
        if len(message) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"메시지는 {MAX_MESSAGE_LENGTH}자 이하로 입력해 주세요.")
        timestamp = due_at.timestamp()
        cursor = self.connection.execute("""
            INSERT INTO reminders (user_id, channel_id, message, due_at, next_attempt_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, channel_id, message, timestamp, timestamp))
        self.connection.commit()
        return cursor.lastrowid

    def due(self, now: float) -> list[tuple]:
        return self.connection.execute("""
            SELECT id, user_id, channel_id, message FROM reminders
            WHERE status = 'pending' AND next_attempt_at <= ?
            ORDER BY next_attempt_at, id LIMIT 100
        """, (now,)).fetchall()

    def finish(self, reminder_id: int, status: str = "sent"):
        self.connection.execute("UPDATE reminders SET status = ? WHERE id = ?", (status, reminder_id))
        self.connection.commit()

    def retry(self, reminder_id: int, now: float):
        self.connection.execute("UPDATE reminders SET next_attempt_at = ? WHERE id = ?",
                                (now + 60, reminder_id))
        self.connection.commit()
