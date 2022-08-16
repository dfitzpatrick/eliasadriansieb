import pathlib

import aiosqlite
import pytest_asyncio

from data.crud import execute_script


@pytest_asyncio.fixture
async def memdb():
    create_script = pathlib.Path(__file__).parents[1] / 'data/scripts/create.sql'
    async with aiosqlite.connect(':memory:') as db:
        await execute_script(db, create_script)
        yield db
