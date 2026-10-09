from typing import Protocol
from .dto import AssignmentInput, MembershipResponse


class OrganizationRepository(Protocol):
    def assign(self, group_id: str, data: AssignmentInput, actor_id: str) -> list[MembershipResponse]: ...
    def remove(self, group_id: str, animal_id: str, effective_date, actor_id: str) -> MembershipResponse: ...
