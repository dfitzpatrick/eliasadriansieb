from datetime import timedelta

import discord
from discord import Interaction

from bot.pagination import LongDescriptionPaginator


def td_format(td_object: timedelta):
    """
    Taken from https://stackoverflow.com/questions/538666/format-timedelta-to-string
    Just make it more human readable
    Parameters
    ----------
    td_object

    Returns
    -------

    """
    seconds = int(td_object.total_seconds())
    periods = [
        ('year',        60*60*24*365),
        ('month',       60*60*24*30),
        ('day',         60*60*24),
        ('hour',        60*60),
        ('minute',      60),
        ('second',      1)
    ]

    strings=[]
    for period_name, period_seconds in periods:
        if seconds > period_seconds:
            period_value , seconds = divmod(seconds, period_seconds)
            has_s = 's' if period_value > 1 else ''
            strings.append("%s %s%s" % (period_value, period_name, has_s))

    return ", ".join(strings)

async def send_safe_embed(itx: Interaction, embed: discord.Embed):
    if len(embed.description) > 4000:
        await itx.response.send_message(
            embed=embed,
            ephemeral=True,
            view=await LongDescriptionPaginator(itx.client, itx.user, embed.title, embed.description, 2000).run()
        )
    else:
        await itx.response.send_message(embed=embed, ephemeral=True)