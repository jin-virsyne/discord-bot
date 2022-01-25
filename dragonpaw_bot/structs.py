import datetime
from typing import List, Mapping, Optional, Tuple

import hikari
import pydantic


# ---------------------------------------------------------------------------- #
#             Configs: The format that we get from the config file.            #
# ---------------------------------------------------------------------------- #
class LobbyConfig(pydantic.BaseModel):
    channel: str
    click_for_rules: bool = False
    kick_after_days: Optional[int]
    role: Optional[str]
    rules: Optional[str]
    welcome_message: Optional[str]


class RoleMenuOptionConfig(pydantic.BaseModel):
    role: str
    emoji: str
    description: str


class RoleMenuConfig(pydantic.BaseModel):
    name: str
    single: bool = False
    description: Optional[str]
    options: List[RoleMenuOptionConfig]


class RolesConfig(pydantic.BaseModel):
    channel: str
    menu: List[RoleMenuConfig]


class GuildConfig(pydantic.BaseModel):
    lobby: Optional[LobbyConfig]
    roles: Optional[RolesConfig]
    log_channel: Optional[str]


# ---------------------------------------------------------------------------- #
#              States: The thing we keep after seting up the Guild             #
# ---------------------------------------------------------------------------- #
class RoleMenuOptionState(pydantic.BaseModel):
    add_role_id: hikari.Snowflake
    remove_role_ids: List[hikari.Snowflake]


class GuildState(pydantic.BaseModel):
    id: hikari.Snowflake
    name: str

    config_url: str
    # config_size: int
    config_last: datetime.datetime

    lobby_role_id: Optional[hikari.Snowflake] = None
    lobby_welcome_message: Optional[str] = None
    lobby_channel_id: Optional[hikari.Snowflake] = None
    lobby_click_for_rules: bool = False
    lobby_kick_days: int = 0
    lobby_rules: str = ""
    lobby_rules_message_id: Optional[hikari.Snowflake] = None

    # Role management
    role_channel_id: Optional[hikari.Snowflake] = None
    # Key is (meddage.id,emoji)
    role_emojis: Mapping[Tuple[hikari.Snowflake, str], RoleMenuOptionState]
    role_names: Mapping[hikari.Snowflake, str]

    log_channel_id: Optional[hikari.Snowflake] = None
