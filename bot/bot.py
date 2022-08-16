import logging
import pathlib

import aiosqlite
from discord.ext import commands

from data.crud import execute_script

log = logging.getLogger(__name__)
extensions = (
    'bot.core',
    'bot.challenge',
)


class ChallengeBot(commands.Bot):

    def __init__(self, *args, **kwargs):
        super(ChallengeBot, self).__init__(*args, **kwargs)
        self.data_path = pathlib.Path(__file__).parents[1]
        self.db_path = self.data_path / 'data/challenge.sqlite'
        self.db_scripts = self.data_path / 'data/scripts'

    async def setup_hook(self) -> None:
        # Create the database if it doesn't exist
        async with aiosqlite.connect(self.db_path) as db:
            await execute_script(db, self.db_scripts / 'create.sql')
        log.debug("Tables created")
        for ext in extensions:
            await self.load_extension(ext)
            log.debug(f"Extension {ext} loaded")