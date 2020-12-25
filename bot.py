# bot.py
import dataclasses
import os
from collections import defaultdict
from typing import Dict, List

import discord
import emojis
import palettable
import yaml
from dotenv import load_dotenv
from loguru import logger
from palettable.mycarta import get_map

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
COLORS = "Cube1_{}"
# COLORS = "Viridis"
# GUILD = os.getenv('DISCORD_GUILD')


def list_int() -> List[int]:
    return []


class AshBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.auto_add_roles: Dict[int, List[int]] = {}
        self.role_channel: Dict[int, int] = {}
        self.role_messages: Dict[int, List[int]] = defaultdict(list_int)
        self.role_mapping: Dict[int, Dict[int, discord.Role]] = defaultdict(dict)
        self.emoji: Dict[int, Dict[str, discord.Emoji]] = defaultdict(dict)

    async def on_ready(self):
        # guild = discord.utils.get(client.guilds, name=GUILD)
        logger.info(f"{client.user} has connected to Discord!")
        for guild in client.guilds:

            # Find the role channel.
            # logger.info(f'{guild.name}(id: {guild.id})')
            for c in guild.channels:
                if c.type != discord.ChannelType.text:
                    continue
                logger.debug(f"  Channel: {c.name}")
                if c.name == "roles":
                    self.role_channel[guild.id] = c
                    logger.info(f"Found #roles: {c.id}")
                    break

            # Did we find the channel for roles?
            if not self.role_channel[guild.id]:
                continue

            for emoji in self.emojis:
                logger.debug("--Client Emoji: {}", emoji.name)
                self.emoji[guild.id][emoji.name] = emoji
            for emoji in guild.emojis:
                logger.debug("--Custom Emoji: {}", emoji.name)
                self.emoji[guild.id][emoji.name] = emoji

            channel = self.role_channel[guild.id]
            async for message in channel.history(limit=200):
                logger.debug(f"Considering role message: {message}")
                if message.author != client.user:
                    continue
                logger.info("- Is from me.")
                self.role_messages[guild.id].append(message)
            await self.setup_roles(guild)

    async def on_member_join(self, member):
        if member.guild.id in self.auto_add_roles:
            await member.add_roles(roles=self.auto_add_roles[member.guild.id])

        # await member.create_dm()
        # await member.dm_channel.send(
        #     f'Hi {member.name}, welcome to my Discord server!'
        # )

    # async def on_message(self, message):
    #     logger.debug(f"New message: {message}")

    async def on_reaction_add(self, reaction, member):
        if hasattr(reaction.emoji, "name"):
            emoji = reaction.emoji.name
        else:
            emoji = reaction.emoji
        logger.debug(f"Reaction: {emoji!r} on {reaction.message.id} from {member.id}")
        if member == client.user:
            return

    async def on_guild_emojis_update(self, guild, before, after):
        pass

    async def delete_my_messages(self, guild):
        if not self.role_messages[guild.id]:
            return

        await self.role_channel[guild.id].delete_messages(self.role_messages[guild.id])

    def valid(self, data):
        return True

    async def setup_roles(self, guild):
        await self.delete_my_messages(guild)
        channel = self.role_channel[guild.id]
        with open(channel.name + ".yaml", "r") as f:
            data = yaml.load(f.read(), Loader=yaml.Loader)
        if not self.valid(data):
            return

        colors = get_map(COLORS.format(len(data))).colors
        for x in range(len(data)):
            menu = data[x]
            embed = discord.Embed(
                color=discord.Color.from_rgb(*colors[x]),
                title=menu["title"],
                description=menu.get("description", None),
            )
            for d in menu["options"]:
                e = d["emoji"]
                description = d["description"]
                name = d["role"]
                embed.add_field(
                    name=name, value=f":{e}: {description}\n_ _\n", inline=False
                )
            message = await channel.send(embed=embed)
            for d in menu["options"]:
                code = d["emoji"]
                # Is it a stock one?
                e = emojis.db.get_emoji_by_alias(code)
                if e:
                    e = e.emoji
                else:
                    # Then a custom one?
                    e = self.emoji[guild.id].get(code, None)
                if not e:
                    logger.error("Emoji {} is unknown on this server.", d["emoji"])
                    continue
                logger.debug("Adding: {}", e)
                await message.add_reaction(e)


intents = discord.Intents.default()
intents.guilds = True
intents.reactions = True
intents.messages = True
# intents.emoji = True
client = AshBot(intents=intents)
client.run(TOKEN)
