import discord
import os
from discord.ext import commands
import asyncio
import logging
from .bot import ChallengeBot
log = logging.getLogger(__name__)



def bot_task_callback(future: asyncio.Future):
    if future.exception():
        raise future.exception()


async def run_bot():
    token = os.environ['TOKEN']
    intents = discord.Intents.all()
    intents.message_content = True
    intents.members = True
    bot = ChallengeBot(
        intents=intents,
        command_prefix='!',
        slash_commands=True,
    )
    try:
        await bot.start(token)
    finally:
        await bot.close()

loop = asyncio.new_event_loop()
try:
    future = asyncio.ensure_future(
        run_bot(),
        loop=loop
    )
    future.add_done_callback(bot_task_callback)
    loop.run_forever()
except KeyboardInterrupt:
    pass
finally:
    loop.close()
