from data.crud import *
import pytest

def test_challenge_object():
    d = datetime.now()
    c = Challenge(1,d.isoformat(), 123, 456, 789, "solo")
    assert isinstance(c.created, datetime)
    assert d == c.created
    assert c.responded_at is None
    c._responded_at_str = d.isoformat()
    assert isinstance(c.responded_at, datetime)

@pytest.mark.asyncio
async def test_insert_challenge(memdb):
    challenge = await insert_challenge(memdb, 123456, 123456, 123456, "solo")
    cursor: aiosqlite.Cursor = await memdb.execute('select * from challenges')
    row = await cursor.fetchone()
    assert row[2] == 123456
    assert row[2] == challenge.guild_id
    assert isinstance(challenge.created, datetime)





@pytest.mark.asyncio
async def test_respond_challenge(memdb):
    challenge = await insert_challenge(memdb, 123456, 123456, 123456, "solo")
    updated = await respond_to_challenge(memdb, 123456, 789011)
    cursor = await memdb.execute('select responded_at, responding_member_id from challenges')
    row = await cursor.fetchone()
    assert row[0] is not None and row[1] == 789011
    assert challenge.responded_at != updated.responded_at
    assert updated.responding_member_id == 789011
    assert challenge.responded_at is None
    assert isinstance(updated.responded_at, datetime)
    with pytest.raises(ChallengeResponded):
        await respond_to_challenge(memdb, 123456, 111111)


@pytest.mark.asyncio
async def test_fetch_all_challenges(memdb):
    await insert_challenge(memdb, 123456, 123456, 123456, "solo")
    await insert_challenge(memdb, 3434, 3434, 324324, "solo")
    await insert_challenge(memdb, 12312452346, 4632324, 346346346, "solo")
    challenges = await fetch_all_challenges(memdb)
    assert len(challenges) == 3


@pytest.mark.asyncio
async def test_fetch_all_unresponded_challenges(memdb):
    await insert_challenge(memdb, 123456, 1234565, 123456, "solo")
    await insert_challenge(memdb, 3434, 3434, 324324, "solo")
    await insert_challenge(memdb, 12312452346, 4632324, 346346346, "solo")
    await memdb.commit()
    await respond_to_challenge(memdb, 123456, 99999)
    await memdb.commit()
    challenges = await fetch_all_challenges(memdb, unresponded_only=True)
    assert len(challenges) == 2

@pytest.mark.asyncio
async def test_create_role(memdb):
    role = await create_match_type_role(memdb, 1234, "solo", 5678)
    assert role.role_id == 5678
    assert role.match_type == 'solo'
    assert role.guild_id == 1234

@pytest.mark.asyncio
async def test_delete_role(memdb):
    role = await create_match_type_role(memdb, 1234, "solo", 5678)
    cursor = await memdb.execute("select count(id) from match_type_roles")
    result = await cursor.fetchone()
    assert result[0] == 1
    await delete_match_type_role(memdb, role.id)
    cursor = await memdb.execute("select count(id) from match_type_roles")
    result = await cursor.fetchone()
    assert result[0] == 0

@pytest.mark.asyncio
async def test_fetch_roles(memdb):
    await create_match_type_role(memdb, 1234, "solo", 5678)
    await create_match_type_role(memdb, 34342, "solo", 22223)
    await create_match_type_role(memdb, 34325, "solo", 6347476347)
    roles = await fetch_roles(memdb)
    assert len(roles) == 3


@pytest.mark.asyncio
async def test_fetch_last_days_completed_challenges(memdb):
    now = datetime.now(timezone.utc)
    await insert_challenge(memdb, 123456, 1234565, 111, "solo", created_at=(now-timedelta(days=5)).isoformat())
    await insert_challenge(memdb, 3434, 3434, 222, "solo", created_at=(now-timedelta(days=5)).isoformat())
    await insert_challenge(memdb, 12312452346, 4632324, 333, "solo", created_at=(now-timedelta(days=3)).isoformat())
    await insert_challenge(memdb, 123456, 1234565, 444, "solo", created_at=(now-timedelta(days=2)).isoformat())
    await insert_challenge(memdb, 3434, 3434, 555, "solo", created_at=(now-timedelta(days=1)).isoformat())
    await insert_challenge(memdb, 12312452346, 4632324, 666, "solo", created_at=(now-timedelta(days=0)).isoformat())
    await memdb.commit()
    await respond_to_challenge(memdb, 111, 99999)
    await respond_to_challenge(memdb, 222, 99999)
    await respond_to_challenge(memdb, 333, 99999)
    await respond_to_challenge(memdb, 444, 99999)
    await respond_to_challenge(memdb, 555, 99999)
    await memdb.commit()
    challenges = await fetch_last_days_completed_challenges(memdb, days=3)
    assert len(challenges) == 3
