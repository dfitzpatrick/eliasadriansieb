import logging
import re
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, TypeAlias, Dict, List, Optional

import aiosqlite
import discord
from discord import app_commands, Interaction
from discord.ext import commands

from data import crud
from data.crud import insert_challenge, respond_to_challenge, Challenge, MatchTypeRole, create_match_type_role, \
    delete_match_type_role, fetch_challenge
from .common import td_format, send_safe_embed
from .pagination import LongDescriptionPaginator

if TYPE_CHECKING:
    from .bot import ChallengeBot


MessageId: TypeAlias = int
GuildId: TypeAlias = int
MATCH_TYPE_REGEX = re.compile(r'Type: .* (Solo Ultra|Solo)')
MATCH_TYPE_CHOICES = [
    app_commands.Choice(name='Solo', value='solo'),
    app_commands.Choice(name='Solo Ultra', value='solo ultra')
]

log = logging.getLogger(__name__)


class ChallengeCog(commands.Cog):
    TIME_OUT_MINUTES = 1

    def __init__(self, bot: 'ChallengeBot'):
        self.bot = bot
        self.challenges: Dict[MessageId, Challenge] = {}
        self.match_roles: Dict[GuildId, List[MatchTypeRole]] = {}
        self._first_run = True

    async def cog_load(self) -> None:
        """Loads all the items from the database into local memory cache
        The database acts to serialize data to disk safely and to allow the bot to recover.
        I do not anticipate high memory consumption with this approach, but it will prevent us
        from pinging the database on each message.
        """
        async with aiosqlite.connect(self.bot.db_path) as db:
            challenges = await crud.fetch_all_challenges(db, unresponded_only=True)
            match_type_roles = await crud.fetch_roles(db)
            self.challenges = {c.message_id:c for c in challenges}
            for mr in match_type_roles:
                if mr.guild_id not in self.match_roles.keys():
                    self.match_roles[mr.guild_id] = []
                self.match_roles[mr.guild_id].append(mr)

    async def clean_missing_roles(self):
        """A utility to help clean up any roles deleted in case the bot was offline
        In the case that the guild cannot be found because the bot was removed, we will retain
        the settings in case the bot is invited back
        """
        await self.bot.wait_until_ready()
        for guild_id, match_roles in self.match_roles.items():
            guild = discord.utils.get(self.bot.guilds, id=guild_id)
            if guild is not None:
                for mr in match_roles:
                    role = discord.utils.get(guild.roles, id=mr.role_id)
                    if role is None:
                        await self.remove_role(guild_id, mr.id)

    def is_match_request(self, message: discord.Message):
        """Used to tell if the message content is a match request. This should probably
        be later incorporated to have a specific user id that is attached to it.
        """
        return 'new match request received!' in message.content.lower()

    async def create_new_challenge(self, message: discord.Message, match_type: str):
        """Registers the new challenge in the database and updates the memory cache"""
        async with aiosqlite.connect(self.bot.db_path) as db:
            challenge = await insert_challenge(db, message.guild.id, message.channel.id, message.id, match_type)
            self.challenges[challenge.message_id] = challenge

    async def answer_challenge(self, challenge: Challenge, responding_member: discord.Member):
        """Updates the registered challenge to show the respondent and updates the memory cache"""
        async with aiosqlite.connect(self.bot.db_path) as db:
            updated_challenge = await respond_to_challenge(db, challenge.message_id, responding_member.id)
            log.debug(updated_challenge.responding_member_id)
            log.debug(updated_challenge.responded_at)
            log.debug(updated_challenge.is_open)
            log.debug(updated_challenge._responded_at_str)

            self.challenges[updated_challenge.message_id] = updated_challenge
            log.debug(self.challenges)

    async def add_role(self, guild_id: int, match_type: str, role_id: int):
        """Adds a role for a certain match type and updates the memory cache"""
        async with aiosqlite.connect(self.bot.db_path) as db:
            match_role = await create_match_type_role(db, guild_id, match_type, role_id)
            if guild_id not in self.match_roles.keys():
                self.match_roles[guild_id] = []
            self.match_roles[guild_id].append(match_role)

    async def remove_role(self, guild_id: int, identifier: int):
        """Removes a role for a certain match type and updates the memory cache"""
        async with aiosqlite.connect(self.bot.db_path) as db:
            await delete_match_type_role(db, identifier)
            if guild_id not in self.match_roles.keys():
                self.match_roles[guild_id] = []
            roles = self.match_roles[guild_id]
            self.match_roles[guild_id] = [mr for mr in roles if mr.id != identifier]

    def get_guild_roles(self, guild: discord.Guild, match_type: Optional[str] = None) -> List[discord.Role]:
        """Transforms the memory cache into discord.Role objects that we can use natively"""
        roles = self.match_roles.get(guild.id, [])
        if match_type is not None:
            roles = [discord.utils.get(guild.roles, id=mr.role_id) for mr in roles if mr.match_type == match_type]
        else:
            roles = [discord.utils.get(guild.roles, id=mr.role_id) for mr in roles]
        return [r for r in roles if r is not None]

    @app_commands.command(name='set-role', description="Adds/Removes a role to ping with a match type")
    @app_commands.choices(match_type=MATCH_TYPE_CHOICES)
    @app_commands.checks.has_permissions(manage_roles=True)
    async def set_role_cmd(self, itx: Interaction, match_type: str, role: discord.Role):
        """App command that will set a role to be pinged for a match_type if it times out"""
        guild_roles = self.match_roles.get(itx.guild_id, [])
        roles_mapping = {r.role_id:r.id for r in guild_roles if r.match_type == match_type}
        if role.id in roles_mapping.keys():
            await self.remove_role(itx.guild_id, roles_mapping[role.id])
            await itx.response.send_message(f"(-) {role.name}", ephemeral=True)
        else:
            await self.add_role(itx.guild_id, match_type, role.id)
            await itx.response.send_message(f"(+) {role.name}", ephemeral=True)

    @set_role_cmd.error
    async def set_role_cmd_error(self, itx: Interaction, error):
        original_error = error.original
        if isinstance(original_error, app_commands.CheckFailure):
            await itx.response.send_message("You need to have Manage Roles permission to use this command", ephemeral=True)
        else:
            raise error

    @app_commands.command(name='list-roles', description="Shows which roles are registered for each match type")
    @app_commands.choices(match_type=MATCH_TYPE_CHOICES)
    async def list_roles(self, itx: Interaction, match_type: str):
        """Shows the roles that will ping for a given match_type if it timesout"""
        roles = self.get_guild_roles(itx.guild, match_type)
        description = '\n'.join([r.name for r in roles])
        embed = discord.Embed(title=f"Pinging Roles for {match_type}", description=description)
        await itx.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='open', description="Shows open matches that need to be accepted")
    async def open_matches_cmd(self, itx: Interaction):
        """Proof of concept command that shows all un-answered matches to a user"""
        log.debug(self.challenges)
        lines = []
        for c in sorted(self.challenges.values(), key=lambda o: o.created):
            if not c.guild_id == itx.guild_id or not c.is_open:
                continue
            guild = itx.guild
            channel = guild.get_channel(c.text_channel_id)
            message = channel and channel.get_partial_message(c.message_id)
            if message is not None:
                challenge_type = c.challenge_type.capitalize()
                elapsed = datetime.now(timezone.utc) - c.created
                elapsed = td_format(elapsed)
                text = f"[{challenge_type}]({message.jump_url}): {elapsed}"
                lines.append(text)
        embed = discord.Embed(title="Open Matches", description='\n'.join(lines) or "No Open matches")
        await send_safe_embed(itx, embed)

    @app_commands.command(name='history', description="See the history of completed matches")
    async def history_cmd(self, itx: Interaction, days: int = 3):
        lines = []
        async with aiosqlite.connect(self.bot.db_path) as db:
            challenges = await crud.fetch_last_days_completed_challenges(db, itx.guild_id, days)
        deltas = [c.elapsed for c in challenges]
        average_completion = sum(deltas, timedelta(0)) / len(deltas) if len(deltas) > 0 else "(No Average)"
        average_completion = td_format(average_completion)
        for c in sorted(challenges, key=lambda o: o.created):
            channel = itx.guild.get_channel(c.text_channel_id)
            message = channel and channel.get_partial_message(c.message_id)
            challenge_date = c.created.strftime("%Y-%m-%d")
            respondent = itx.guild.get_member(c.responding_member_id)
            respondent = respondent and respondent.display_name or "Member Left Server"
            challenge_type = c.challenge_type.capitalize()
            elapsed = td_format(c.elapsed)
            if message:
                text = f"[{challenge_date}/{challenge_type}/{respondent}]({message.jump_url}):  {elapsed}"
            else:
                text = f"{challenge_date}/{challenge_type}/{respondent} (Msg Deleted):  {elapsed}"
            lines.append(text)
        count = len(challenges)
        title = f"{count} Completed Challenges over {days} days Avg: {average_completion}"
        embed = discord.Embed(title=title, description='\n'.join(lines) or "No History")
        await send_safe_embed(itx, embed)


    @commands.Cog.listener()
    async def on_new_challenge(self, message: discord.Message, match_type: str):
        """A new challenge message was detected in the chat"""
        await self.create_new_challenge(message, match_type)
        await message.channel.send(f"This is a placeholder to show I received the message. Timeout is currently {self.TIME_OUT_MINUTES} minute")
        await discord.utils.sleep_until(datetime.now(timezone.utc) + timedelta(minutes=self.TIME_OUT_MINUTES))
        challenge = self.challenges.get(message.id)
        if challenge is None:
            # Missing from local. Perhaps the bot died?
            async with aiosqlite.connect(self.bot.db_path) as db:
                challenge = await fetch_challenge(message.id)
                if challenge is None:
                    # Still cannot find the challenge. Don't fire the event since it was never recorded
                    return
                self.challenges[message.id] = challenge
        if challenge.is_open:
            self.bot.dispatch("challenge_timeout", challenge, message)

    @commands.Cog.listener()
    async def on_challenge_timeout(self, challenge: Challenge, message: discord.Message):
        """A challenge has gone past the timeout. This currently removes the item from the cache
        when this happens and the roles are pinged in a reply to the original message"""
        del self.challenges[challenge.message_id]
        guild = discord.utils.get(self.bot.guilds, id=challenge.guild_id)
        if guild is not None:
            roles = self.get_guild_roles(guild, challenge.challenge_type)
            role_mentions = ' '.join(r.mention for r in roles)
            await message.reply(f"{role_mentions} This order is still up!")

    @commands.Cog.listener()
    async def on_challenge_accepted(self, challenge: Challenge, message: discord.Message):
        """Fires when a person accepts a challenge. Records the challenge to the database"""
        await self.answer_challenge(challenge, message.author)
        await message.channel.send(f"I see you! {message.author.mention}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Utility event to remove any roles from the database or memory cache if its deleted from the guild"""
        guild_id = role.guild.id
        for r in self.match_roles.get(guild_id, []):
            if r.role_id == role.id:
                await self.remove_role(guild_id, r.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Intercepts a message and determines if it is a new challenge or a challenge acceptance"""
        if message.author == self.bot.user:
            return
        if self.is_match_request(message):
            match_type = re.search(MATCH_TYPE_REGEX, message.content)
            log.debug("Dispatching new challenge")
            self.bot.dispatch('new_challenge', message, match_type[1])
            return
        ref_id = message.reference and message.reference.message_id
        challenge = self.challenges.get(ref_id)
        if challenge is not None and 'accept' in message.content.lower():
            self.bot.dispatch('challenge_accepted', challenge, message)

    @commands.Cog.listener()
    async def on_ready(self):
        """Fires each time the bot connects which can be fired multiple times. We use a flag to see if its from
        the bot loading up. This runs a utility script to help clean the roles once the internal discord
        cache is loaded"""

        if self._first_run:
            await self.clean_missing_roles()
            self._first_run = False


async def setup(bot: 'ChallengeBot'):
    await bot.add_cog(ChallengeCog(bot))