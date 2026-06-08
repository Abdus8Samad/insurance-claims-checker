"""Member roster lookup, sourced from the `members` array in policy_terms.json."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel


class Member(BaseModel):
    member_id: str
    name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    relationship: Optional[str] = None
    join_date: Optional[date] = None
    primary_member_id: Optional[str] = None
    dependents: list[str] = []


class MemberNotFoundError(LookupError):
    pass


class MemberRoster:
    def __init__(self, members: list[Member]):
        self._by_id = {m.member_id: m for m in members}

    @classmethod
    def from_policy_raw(cls, raw: dict[str, Any]) -> "MemberRoster":
        members = [Member(**m) for m in raw.get("members", [])]
        return cls(members)

    def get(self, member_id: str) -> Member:
        if member_id not in self._by_id:
            raise MemberNotFoundError(member_id)
        return self._by_id[member_id]

    def exists(self, member_id: str) -> bool:
        return member_id in self._by_id

    def all(self) -> list[Member]:
        return list(self._by_id.values())
