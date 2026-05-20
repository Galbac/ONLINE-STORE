from pydantic import BaseModel


class AdminRoleResponse(BaseModel):
    code: str
    name: str
    description: str
    permissions: list[str]


class AdminRoleListResponse(BaseModel):
    items: list[AdminRoleResponse]
