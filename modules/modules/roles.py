from __future__ import annotations

import os
import logging
from dataclasses import dataclass

import discord

from modules.database import Database


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProgressionRole:
    role_id: int
    minimum_total_level: int


class RoleManager:
    """Applies one highest qualifying progression role per member.

    Configure roles with PROGRESSION_ROLES like:
    111111111111111111:1000,222222222222222222:1500,333333333333333333:2000
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self.progression_roles = _load_progression_roles()

    async def apply_highest_progression_role(self, member: discord.Member, stats: dict) -> bool:
        if not self.progression_roles:
            return False

        total_level = stats.get("skills", {}).get("overall", {}).get("level", 0)
        target = self._highest_role_for_level(total_level)
        managed_ids = {role.role_id for role in self.progression_roles}
        current_ids = {role.id for role in member.roles}

        roles_to_remove = [
            role for role in member.roles if role.id in managed_ids and (not target or role.id != target.role_id)
        ]
        role_to_add = None
        if target and target.role_id not in current_ids:
            role_to_add = member.guild.get_role(target.role_id)
            if not role_to_add:
                LOGGER.warning(
                    "Progression role ID %s is configured but does not exist in guild %s.",
                    target.role_id,
                    member.guild.id,
                )

        bot_member = member.guild.me
        planned_roles = [*roles_to_remove, *([role_to_add] if role_to_add else [])]
        if bot_member:
            unmanageable = [role for role in planned_roles if role >= bot_member.top_role]
            if unmanageable:
                LOGGER.warning(
                    "Cannot update progression role for %s because the bot role is not above: %s",
                    member.id,
                    ", ".join(role.name for role in unmanageable),
                )
                return False

        # Avoid no-op role edits so Discord audit logs stay clean.
        if not roles_to_remove and not role_to_add:
            return False

        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="OSRS progression role update")
        if role_to_add:
            await member.add_roles(role_to_add, reason="OSRS progression role update")
        return True

    def _highest_role_for_level(self, total_level: int) -> ProgressionRole | None:
        eligible = [role for role in self.progression_roles if total_level >= role.minimum_total_level]
        return eligible[-1] if eligible else None


def _load_progression_roles() -> list[ProgressionRole]:
    raw = os.getenv("PROGRESSION_ROLES", "").strip()
    roles: list[ProgressionRole] = []
    if not raw:
        return roles

    for chunk in raw.split(","):
        role_id, minimum = chunk.split(":", 1)
        roles.append(ProgressionRole(role_id=int(role_id), minimum_total_level=int(minimum)))

    return sorted(roles, key=lambda role: role.minimum_total_level)
