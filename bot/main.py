#!/usr/bin/env python
import asyncio
import dataclasses
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple

import aiohttp
import discord
import dotenv
import emojis
import palettable
import yamale
import yaml
from loguru import logger

ROOT_DIR = Path(__file__).resolve().parent.parent

dotenv.load_dotenv(ROOT_DIR / ".env")

TOKEN = os.getenv("DISCORD_TOKEN")
COLORS = "Cube1_{}"  # https://jiffyclub.github.io/palettable/
SCHEMA = yamale.make_schema(ROOT_DIR / "bot/schema.yaml")
VALIDATION_ERROR = (
    "The config for this server failed to pass validation. Below are the errors. "
    "(Please be aware, programmers start counting at 0, so `menus.1.description` "
    "means the description of your **2nd** menu!"
)
ROLE_NOTE = (
    "**Using role menus:**\n"
    "Please click/tap on the reactions above to pick the roles you'd like. "
    "Doing so will add those server roles to you.\n"
    "_ _\n"
    "**Note:** From time to time these messages will be deleted, when roles are updated."
    "You do not need to re-select roles to keep them."
)
SINGLE_ROLE_MENU = (
    "**Note:** You can only pick a single option from this list. "
    "Choosing a new one will remove all the others from your profile."
)
OAUTH_PERMISSIONS = 268511296
OAUTH_URL = f"https://discord.com/api/oauth2/authorize?client_id=791831545475235860&permissions={OAUTH_PERMISSIONS}&scope=bot"


def list_int() -> List[int]:
    return []


# TODO: https://discordpy.readthedocs.io/en/latest/ext/commands/cogs.html

# def emoji_from_reaction(reaction: discord.Reaction):
#     if reaction.custom_emoji:
#         emoji_name = reaction.emoji.name
#     else:
#         emoji_name = emojis.decode(reaction.emoji).strip(":")
#     return emoji_name


def emoji_from_partial(partial: discord.PartialEmoji):
    if partial.is_custom_emoji():
        emoji_name = partial.name
    else:
        emoji_name = emojis.decode(partial.name).strip(":")
    return emoji_name


@dataclasses.dataclass
class ConfigMeta:
    url: str
    size: int
    last: int


@dataclasses.dataclass
class RoleMenuOption:
    role: discord.Role
    role_name: str
    emoji: str
    description: str


@dataclasses.dataclass
class RoleMenu:
    name: str
    description: str = None
    options: List[RoleMenuOption] = dataclasses.field(default_factory=list)
    single: bool = False
    message: discord.Message = None

    # def for_reaction(self, reaction):
    #     return discord.utils.get(self.options, emoji=emoji_from_reaction(reaction))

    def for_partial(self, partial):
        return discord.utils.get(self.options, emoji=emoji_from_partial(partial))


@dataclasses.dataclass
class GuildInfo:
    id: int
    name: str
    guild: discord.Guild = None
    meta: ConfigMeta = None
    role_channel: discord.TextChannel = None
    config_errors: List[str] = dataclasses.field(default_factory=list)
    emoji: Dict[str, discord.Emoji] = dataclasses.field(default_factory=dict)
    menus: List[RoleMenu] = dataclasses.field(default_factory=list)
    new_member_role: discord.Role = None
    roles: Dict[str, discord.Role] = dataclasses.field(default_factory=dict)
    role_messages: Dict[discord.Message, RoleMenu] = dataclasses.field(
        default_factory=dict
    )

    def get_emoji(self, name):
        e = emojis.db.get_emoji_by_alias(name)

        if name in self.emoji:
            return self.emoji.get(name)
        elif e:
            return e.emoji
        else:
            return None

    def role_menu_by_id(self, message_id: int):
        for message, menu in self.role_messages.items():
            if message_id == message.id:
                return menu
        return None

    def load_emoji(self):
        self.emoji = {}
        # Load the emojis!
        # for emoji in self.emojis:
        #     logger.debug("--Client Emoji: {}", emoji.name)
        #     gi.emoji[emoji.name] = emoji
        for emoji in self.guild.emojis:
            logger.debug("Guild has a custom Emoji: {}", emoji.name)
            self.emoji[emoji.name] = emoji

    def load_roles(self, data, guild: discord.Guild):

        if "new_member_role" in data:
            self.new_member_role = discord.utils.get(
                guild.roles, name=data["new_member_role"]
            )

        # If no role channels, then we are done.
        if "role_channel" not in data:
            return

        logger.debug("This guild uses a role channel.")
        self.role_channel = discord.utils.get(
            guild.text_channels, name=data["role_channel"]
        )
        for menu in data["menus"]:
            mi = RoleMenu(
                name=menu["name"],
                description=menu.get("description", ""),
                single=menu.get("single", False),
            )
            self.menus.append(mi)
            for option in menu["options"]:
                role = discord.utils.get(guild.roles, name=option["role"])
                emoji = self.get_emoji(option["emoji"])
                if not role:
                    self.config_errors.append(
                        "The role '{}' (from menu {}) doesn't appear to exist.".format(
                            option["role"], mi.name
                        )
                    )
                    continue
                if not emoji:
                    self.config_errors.append(
                        "The emoji '{}' (from menu {}) doesn't appear to exist.".format(
                            option["emoji"], mi.name
                        )
                    )
                    continue
                mi.options.append(
                    RoleMenuOption(
                        role_name=option["role"],
                        role=role,
                        description=option.get("description", ""),
                        emoji=option["emoji"],
                    )
                )

    @classmethod
    async def from_config(cls, guild):
        gi = cls(
            id=guild.id,
            name=guild.name,
            guild=guild,
            roles={r.name: r for r in guild.roles},
            config_errors=[],
        )

        logger.info("Loading config for guild: {}", guild)
        try:
            data = yamale.make_data(ROOT_DIR / f"data/{guild.id}.yaml")
        except Exception as e:
            gi.config_errors.append(str(e))
            return gi

        try:
            yamale.validate(SCHEMA, data)
        except yamale.YamaleError as e:
            logger.error("Config file failed validation")
            for r in e.results:
                logger.error("Validation error: {} with {}", r.data, r.schema)
                for error in r.errors:
                    logger.error("     {}", error)
                    gi.config_errors.append(f"- {error}")

        # Yamale nests.
        data = data[0][0]

        if "meta" in data:
            gi.meta = ConfigMeta(**data["meta"])

        gi.load_emoji()
        gi.load_roles(data, guild)

        logger.debug("Done loading.")
        return gi


def rainbow(n: int) -> List[Tuple[int, int, int]]:
    # This is how to do it using only colorsys, but the colors are not as nice.
    # end = 2 / 3
    # as_float = [colorsys.hls_to_rgb(end * i / (n - 1), 0.5, 1) for i in range(n)]
    # return [(int(x[0] * 255), int(x[1] * 255), int(x[2] * 255)) for x in as_float]
    return palettable.mycarta.get_map(COLORS.format(n)).colors


class AshBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache: Dict[int, GuildInfo] = {}

    async def on_ready(self):
        """Post-initalization for the bot."""
        logger.info(f"{self.user} has connected to Discord!")
        for guild in self.guilds:
            await self.update_guild_config(guild)
            await self.configure_guild(guild)

    async def on_member_join(self, member: discord.Member):
        """Handle members joining."""
        c = self.cache[member.guild.id]
        if c.new_member_role:
            await member.add_roles(roles=c.new_member_role)

    # async def send_error(self, member: discord.Member, message: str):
    #     """Tell someone that something went wrong."""
    #     await member.create_dm()
    #     await member.dm_channel.send(message)

    async def update_guild_config(self, guild, errors_to=None):
        """Load the config for a guild and start setting up everything there."""

        # Load the config.
        gi: GuildInfo = await GuildInfo.from_config(guild)
        if not gi:
            logger.error("Unable to work with guild: {}", guild)
            return

        # Cache for later
        self.cache[gi.id] = gi

    async def configure_guild(self, guild, errors_to=None):

        c = self.cache[guild.id]

        # Start setting up the guild
        if c.role_channel:
            await self.setup_roles(guild)

        # This happens atfer the setup_roles, else the messages here get deleted by that.
        if c.config_errors:
            await self.report_errors(
                guild, title="Config errors", errors=c.config_errors, to=errors_to
            )

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        if not message.content.startswith("$config"):
            return

        # Ignore DMs
        if not message.guild:
            return

        # await message.channel.send("Hello!")

        c = self.cache[message.guild.id]

        cmd = message.content.split()
        if len(cmd) == 2:
            url = cmd[1]
            await message.channel.send(
                f"Loading config from new URL: {url}", delete_after=20
            )
            try:
                await self.get_config(message.guild, url)
            except aiohttp.client_exceptions.ClientResponseError as e:
                await self.report_errors(
                    guild=message.guild,
                    title="Error downloading config",
                    errors=[str(e)],
                    to=message.channel,
                    emoji="poop",
                )
                return
        else:
            await message.channel.send(
                f"Loading config from prior URL: {c.meta.url}", delete_after=20
            )
            await self.get_config(message.guild, c.meta.url)

        await self.update_guild_config(message.guild, errors_to=message.channel)
        await self.configure_guild(message.guild, errors_to=message.channel)
        await message.delete()

    async def get_config(self, guild: discord.Guild, url: str):
        logger.info("Grabbing new config from: {}", url)

        text = await self.get_text(url)
        data = yaml.load(text, Loader=yaml.Loader)
        if not text:
            return
        logger.debug("Found {}b of text", len(text))
        data["meta"] = {"url": url, "size": len(text), "last": int(time.time())}
        with open(f"data/{guild.id}.yaml", "w") as conf:
            yaml.dump(data, stream=conf)
        return

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Process a possible request for role removal."""
        if self.user.id == payload.user_id:
            return

        c = self.cache[payload.guild_id]

        menu = c.role_menu_by_id(payload.message_id)
        if not menu:
            logger.debug("Not a recognized message_id")
            return

        option = menu.for_partial(payload.emoji)
        if not option:
            logger.warning("Unknown emoji... Don't care that it is gone...")
            return

        logger.debug("And this emoji maps to the role: {}", option.role_name)
        if not option.role:
            logger.warning("Role isn't known on this server.")
            return

        logger.info("Removing role {} from {}", option.role, payload.message_id)
        try:
            await self.http.remove_role(
                payload.guild_id,
                payload.user_id,
                option.role.id,
                reason="Member un-clicked the role menu.",
            )
        except discord.errors.Forbidden:
            logger.error("Unable to remove role, got Forbidden: {}", option.role)
            await self.report_errors(
                c.guild,
                title="Error removing roles",
                errors=[
                    f"Unable to remove role: **{option.role}**, "
                    "please check my permissions relative to that role."
                ],
                emoji="exploding_head",
                to=c.role_channel,
            )

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Process a possible role addition request."""

        if self.user.id == payload.user_id:
            return

        c = self.cache[payload.guild_id]

        menu = c.role_menu_by_id(payload.message_id)
        if not menu:
            logger.debug("Not a recognized message_id")
            return

        option = menu.for_partial(payload.emoji)
        if not option:
            logger.warning("Unknown emoji... Removing it.")
            await self.http.remove_reaction(
                payload.channel_id, payload.message_id, option, payload.user_id
            )

        logger.debug("And this emoji maps to the role: {}", option.role_name)
        if not option.role:
            logger.warning("Role isn't known on this server.")
            return

        nick = payload.member.nick or payload.member.name
        logger.info("Adding role {} to {}", option.role, nick)
        try:
            await payload.member.add_roles(
                option.role, reason="Member clicked on role menu"
            )
        except discord.errors.Forbidden:
            logger.error("Unable to set role, got Forbidden: {}", option.role)
            await self.report_errors(
                c.guild,
                title="Error adding role",
                errors=[
                    f"Unable to set role: **{option.role}**, "
                    "please check my permissions relative to that role."
                ],
                emoji="exploding_head",
                to=c.role_channel,
            )
            return

        # Handle removing other roles and reactions if this is a single-role menu.
        if menu.single:
            remove = [o.role for o in menu.options if o != option]
            remove_emoji = [c.get_emoji(o.emoji) for o in menu.options if o != option]
            logger.info("Removing extra roles/reactions: {}", remove)
            await asyncio.gather(
                payload.member.remove_roles(
                    *remove, reason=f"Member changed to {option.role.name}"
                ),
                *[
                    menu.message.remove_reaction(e, payload.member)
                    for e in remove_emoji
                ],
            )

    async def on_guild_emojis_update(self, guild, before, after):
        """Reload all the emoji."""
        self.cache[guild.id].load_emoji()

    def where_to_complain(self, guild):
        c = self.cache[guild.id]
        if c.role_channel:
            return c.role_channel

        log_channel = discord.utils.get(guild.text_channels, name="log")
        if log_channel:
            return log_channel

        return guild.owner

    async def report_errors(self, guild, title, errors, emoji=None, to=None):
        """Dump all the config errors somewhere, where hopefully they get seen."""
        c = self.cache[guild.id]

        if not to:
            to = self.where_to_complain(guild)

        for error in errors:
            embed = discord.Embed(
                color=discord.Color.dark_red(),
                title=title,
                description=error,
            )
            if emoji:
                embed.description = f":{emoji}: {embed.description}"
            await to.send(embed=embed)

    async def setup_roles(self, guild):
        """Setup the role channel for the guild.

        This wipes out all old role messages I sent, and sends new ones."""
        c = self.cache[guild.id]

        # Delete existing messages
        messages = []
        async for message in c.role_channel.history(limit=200):
            logger.debug(f"Considering role message: {message}")
            if message.author == self.user:
                logger.info("Deleting my role message")
                messages.append(message)
        await c.role_channel.delete_messages(messages)
        c.role_messages = {}

        menu_count = len(c.menus)
        colors = rainbow(menu_count)
        for x in range(menu_count):
            menu = c.menus[x]
            embed = discord.Embed(
                color=discord.Color.from_rgb(*colors[x]),
                title=menu.name,
                description=menu.description,
            )
            if menu.single:
                embed.title += " (Pick 1)"
                if embed.description:
                    embed.description += "\n_ _\n" + SINGLE_ROLE_MENU
                else:
                    embed.description = SINGLE_ROLE_MENU

            for o in menu.options:
                e = c.get_emoji(o.emoji)
                embed.add_field(
                    name=o.role_name,
                    value=f"{e} {o.description}\n_ _\n",
                    inline=False,
                )
            message = await c.role_channel.send(embed=embed)
            menu.message = message
            c.role_messages[message] = menu
            for o in menu.options:

                # Is it a stock one?
                e = c.get_emoji(o.emoji)
                if not e:
                    logger.error("Emoji {} is unknown on this server.", o.emoji)
                    continue
                logger.debug("Adding: {}", e)
                await message.add_reaction(e)
        await c.role_channel.send(content=ROLE_NOTE)

    async def get_json(self, url):
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.get(url) as r:
                if r.status == 200:
                    return await r.json()

    async def get_text(self, url):
        async with aiohttp.ClientSession(raise_for_status=True) as session:
            async with session.get(url) as r:
                return await r.text()


if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.guilds = True
    intents.reactions = True
    intents.messages = True
    intents.emojis = True
    client = AshBot(intents=intents)
    client.run(TOKEN)
