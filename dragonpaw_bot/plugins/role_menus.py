from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Mapping

import hikari
import lightbulb

from dragonpaw_bot import structs, utils
from dragonpaw_bot.colors import rainbow

if TYPE_CHECKING:
    from dragonpaw_bot.bot import DragonpawBot

logger = logging.getLogger(__name__)

ROLE_NOTE = (
    "**Using role menus:**\n"
    "Please click/tap on the reactions above to pick the roles you'd like. "
    "Doing so will add those server roles to you.\n"
    "_ _\n"
    "**Note:** From time to time these messages will be deleted, when roles are "
    "updated."
    "You do not need to re-select roles to keep them."
)
SINGLE_ROLE_MENU = (
    "**Note:** You can only pick a single option from this list. "
    "Choosing a new one will remove all the others from your profile."
)

plugin = lightbulb.Plugin("RoleMenus")
plugin.add_checks(lightbulb.checks.human_only)


def load(bot):
    bot.add_plugin(plugin)


def unload(bot):
    bot.remove_plugin(plugin)


async def configure_role_menus(
    bot: DragonpawBot,
    guild: hikari.Guild,
    config: structs.RolesConfig,
    state: structs.GuildState,
    role_map: Mapping[str, hikari.Role],
) -> List[str]:
    """Setup the role channel for the guild.

    This wipes out all old role messages I sent, and sends new ones."""

    errors: list[str] = []

    channel = await utils.guild_channel_by_name(
        bot=bot, guild=guild, name=config.channel
    )
    if not channel:
        errors.append("Role channel '%s' doesn't seem to exist.")
        return errors

    state.role_channel_id = channel.id
    state.role_emojis = {}

    if not config.menu:
        errors.append("Role channel is set, but no role menus seem to exist.")
        return errors

    emoji_map = await utils.guild_emojis(bot=bot, guild=guild)

    logger.debug("Trying to delete old role menus...")
    await utils.delete_my_messages(
        bot=bot, guild_name=guild.name, channel_id=channel.id
    )

    colors = rainbow(len(config.menu))
    for x, menu in enumerate(config.menu):
        logger.info("G=%r Adding the menu: %s", guild.name, menu.name)
        embed = hikari.Embed(color=hikari.Color.from_rgb(*colors[x]))
        if menu.single:
            embed.title = menu.name + " (Pick 1)"
            if menu.description:
                embed.description = menu.description + "\n_ _\n" + SINGLE_ROLE_MENU
            else:
                embed.description = SINGLE_ROLE_MENU
        else:
            embed.title = menu.name
            embed.description = menu.description

        for o in menu.options:
            e = emoji_map.get(o.emoji)
            if not e:
                errors.append(f"Emoji '{o.emoji}' doesn't seem to exist.")
                continue
            if o.role not in role_map:
                errors.append(f"Role '{o.role}' doesn't seem to exist.")
                continue
            embed.add_field(
                name=o.role,
                value=f"{e.mention} {o.description}\n_ _\n",
                inline=False,
            )
        message = await channel.send(embed=embed)

        for o in menu.options:
            key = (message.id, emoji_map[o.emoji].name)

            if menu.single:
                s = structs.RoleMenuOptionState(
                    add_role_id=role_map[o.role].id,
                    remove_role_ids=[
                        role_map[option.role].id
                        for option in menu.options
                        if option != o
                    ],
                )
            else:
                s = structs.RoleMenuOptionState(
                    add_role_id=role_map[o.role].id,
                    remove_role_ids=[],
                )
            state.role_emojis[key] = s

        # Add the starting reactions
        for o in menu.options:
            e = emoji_map[o.emoji]
            logger.debug("Adding: %s = %s", e, o.role)
            await message.add_reaction(e)

    # The big note at the end.
    await channel.send(content=ROLE_NOTE)
    return errors


@plugin.listener(event=hikari.GuildReactionAddEvent)
async def on_reaction_add(event: hikari.GuildReactionAddEvent):
    """Process a possible role addition request."""

    assert isinstance(plugin.bot, DragonpawBot)

    if not event.emoji_name:
        logger.error("Reaction without an emoji?!: %r", event)
        return

    assert plugin.bot.user_id
    if event.user_id == plugin.bot.user_id:
        return

    assert isinstance(plugin.bot, DragonpawBot)

    c = plugin.bot.state(event.guild_id)
    if not c:
        logger.error("Called on an unknown guild: %r", event.guild_id)
        return

    if isinstance(event.emoji_name, hikari.UnicodeEmoji):
        key = (event.message_id, event.emoji_name.name)
    elif isinstance(event.emoji_name, str):
        key = (event.message_id, event.emoji_name)
    else:
        logger.error("No idea what this emoji is: %r", event.emoji_name)
        return

    if key not in c.role_emojis:
        logger.debug(
            "Unknown emoji %r... Don't care that it is being added...", event.emoji_name
        )
        return
        # TODO: Police the messages I sent for rogue emoji added by users
        # logger.warning("G:%s Unknown emoji on role... Removing it.", c.name)
        # await self.rest.delete_all_reactions_for_emoji(
        #     channel=event.channel_id,
        #     message=event.message_id,
        #     emoji=event.emoji_name,
        # )

    todo = c.role_emojis[key]
    logger.info(
        "G=%r U=%r: Adding role: %s, removing roles: %r",
        c.name,
        event.member.display_name,
        c.role_names[todo.add_role_id],
        [c.role_names[r] for r in todo.remove_role_ids] or None,
    )

    # Add the new role
    try:
        await event.member.add_role(
            role=todo.add_role_id, reason="Member clicked on role menu"
        )
    except hikari.ForbiddenError:
        role = c.role_names[todo.add_role_id]
        await utils.report_errors(
            bot=plugin.bot,
            guild_id=event.guild_id,
            error=(
                f"Unable to add role: **{role}**, "
                "please check my permissions relative to that role."
            ),
        )

    # And maybe remove some old ones.
    for r_id in todo.remove_role_ids:
        try:
            await event.member.remove_role(
                role=r_id, reason="Member clicked on role menu"
            )
        except hikari.ForbiddenError:
            role = c.role_names[r_id]
            await utils.report_errors(
                bot=plugin.bot,
                guild_id=event.guild_id,
                error=(
                    f"Unable to remove role: **{role}**, "
                    "please check my permissions relative to that role."
                ),
            )


@plugin.listener(event=hikari.GuildReactionDeleteEvent)
async def on_reaction_remove(event: hikari.GuildReactionDeleteEvent):
    """Process a possible request for role removal."""

    assert isinstance(plugin.bot, DragonpawBot)

    if event.user_id == plugin.bot.user_id:
        return

    c = plugin.bot.state(event.guild_id)
    if not c:
        logger.error("Called on an unknown guild: %r", event.guild_id)
        return

    if isinstance(event.emoji_name, hikari.UnicodeEmoji):
        key = (event.message_id, event.emoji_name.name)
    elif isinstance(event.emoji_name, str):
        key = (event.message_id, event.emoji_name)
    else:
        logger.error("No idea what this emoji is: %r", event.emoji_name)
        return

    if key not in c.role_emojis:
        logger.debug(
            "Unknown emoji %r... Don't care that it is gone...", event.emoji_name
        )
        return

    # Is this user in the cache?
    cached = plugin.bot.cache.get_member(event.guild_id, event.user_id)
    # If so, this makes the logs nicer
    if cached:
        username = cached.display_name
    else:
        username = str(event.user_id)

    todo = c.role_emojis[key]
    logger.info(
        "G=%r U=%r: Role removed: %s",
        c.name,
        username,
        c.role_names[todo.add_role_id],
    )

    try:
        await plugin.bot.rest.remove_role_from_member(
            guild=c.id,
            user=event.user_id,
            role=todo.add_role_id,
            reason="Member un-clicked the role menu.",
        )
    except hikari.ForbiddenError:
        logger.error("G=%r Unable to remove role, got Forbidden", c.name)
        role = c.role_names[todo.add_role_id]
        await utils.report_errors(
            bot=plugin.bot,
            guild_id=event.guild_id,
            error=(
                f"Unable to remove role: **{role}**, "
                "please check my permissions relative to that role."
            ),
        )
