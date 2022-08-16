from typing import Optional, List

import aiosqlite
from datetime import datetime, timezone, timedelta
import pathlib
from dataclasses import dataclass
from dateutil.parser import parse


class ChallengeResponded(Exception):
    pass


class RoleExists(Exception):
    pass


@dataclass()
class Challenge:
    id: int
    _created_str: str
    guild_id: int
    text_channel_id: int
    message_id: int
    challenge_type: str
    responding_member_id: Optional[int] = None
    _responded_at_str: Optional[str] = None

    @property
    def created(self) -> datetime:
        return parse(self._created_str)

    @property
    def responded_at(self) -> Optional[datetime]:
        if self._responded_at_str is not None:
            return parse(self._responded_at_str)

    @property
    def elapsed(self) -> Optional[timedelta]:
        if self.responded_at is not None:
            elapsed = self.responded_at - self.created
            return elapsed

    @property
    def is_open(self):
        return self.responded_at is None


@dataclass()
class MatchTypeRole:
    id: int
    guild_id: int
    match_type: str
    role_id: int


async def execute_script(db: aiosqlite.Connection, path: pathlib.Path):
    with path.open(mode='r', encoding='utf-8') as sql:
        contents = sql.read()
        await db.executescript(contents)


async def insert_challenge(db: aiosqlite.Connection, guild_id: int, text_channel_id: int, message_id: int, challenge_type: str, created_at: Optional[str] = None) -> Challenge:
    created_at = created_at if created_at is not None else datetime.now(timezone.utc).isoformat()
    sql = "insert into challenges (created, guild_id, text_channel_id, message_id, challenge_type) VALUES (?, ?, ?, ?, ?) RETURNING *"
    cursor = await db.execute(sql, (created_at, guild_id, text_channel_id, message_id, challenge_type.lower()))
    row = await cursor.fetchone()
    await db.commit()
    return Challenge(*row)


async def respond_to_challenge(db: aiosqlite.Connection, challenge_message_id: int, member_id: int) -> Challenge:
    cursor = await db.execute("select responding_member_id from challenges where message_id = ?", (challenge_message_id,))
    row = await cursor.fetchone()
    if row and row[0] is not None:

        raise ChallengeResponded
    responded_at = datetime.now(timezone.utc).isoformat()
    sql = "update challenges set responded_at = ?, responding_member_id = ? where message_id = ? returning *"
    cursor = await db.execute(sql, (responded_at, member_id, challenge_message_id))
    row = await cursor.fetchone()
    await db.commit()
    return Challenge(*row)


async def fetch_challenge(db: aiosqlite.Connection, message_id: int) -> Optional[Challenge]:
    sql = "select * from challenges where message_id = ?"
    cursor = await db.execute(sql, (message_id,))
    row = await cursor.fetchone()
    if row is None:
        return
    return Challenge(*row)


async def fetch_all_challenges(db: aiosqlite.Connection, unresponded_only=False) -> List[Challenge]:
    container = []
    if unresponded_only:
        sql = "select * from challenges where responded_at IS NULL"
    else:
        sql = "select * from challenges"
    async with db.execute(sql) as cursor:
        async for row in cursor:
            container.append(Challenge(*row))
    return container


async def fetch_roles(db: aiosqlite.Connection) -> List[MatchTypeRole]:
    container = []
    sql = "select * from match_type_roles"
    async with db.execute(sql) as cursor:
        async for row in cursor:
            container.append(MatchTypeRole(*row))
    return container


async def create_match_type_role(db: aiosqlite.Connection, guild_id: int, match_type: str, role_id: int) -> MatchTypeRole:
    sql = "insert into match_type_roles (guild_id, match_type, role_id) VALUES (?, ?, ?) returning *"
    try:
        cursor = await db.execute(sql, (guild_id, match_type, role_id))
        row = await cursor.fetchone()
        await db.commit()
        return MatchTypeRole(*row)
    except aiosqlite.IntegrityError:
        raise RoleExists


async def delete_match_type_role(db: aiosqlite.Connection, row_id: int):
    sql = "delete from match_type_roles where id = ?"
    await db.execute(sql, (row_id,))
    await db.commit()


async def fetch_last_days_completed_challenges(db: aiosqlite.Connection, guild_id: Optional[int] = None, days: int = 3) -> List[Challenge]:
    container = []
    fmt = "%Y-%m-%d"
    now = datetime.now(timezone.utc)
    back_days = now - timedelta(days=days)
    now_fmt = now.strftime(fmt)
    back_fmt = back_days.strftime(fmt)

    if guild_id is None:
        sql = "select * from challenges where date(created) BETWEEN ? AND ? and responded_at is not null"
        args = (back_fmt, now_fmt)
    else:
        sql = "select * from challenges where guild_id = ? and  date(created) BETWEEN ? AND ? and responded_at is not null"
        args = (guild_id, back_fmt, now_fmt)
    async with db.execute(sql, args) as cursor:
        async for row in cursor:
            container.append(Challenge(*row))
    return container

