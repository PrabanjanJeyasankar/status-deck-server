from pydantic import BaseModel
from typing import Optional

class ServiceCreateRequest(BaseModel):
    name: str
    organizationId: str
    status: Optional[str] = "OPERATIONAL"
    description: Optional[str] = None

class ServiceUpdateRequest(BaseModel):
    name: Optional[str]
    status: Optional[str]
    description: Optional[str] = None

class ServiceResponse(BaseModel):
    id: str
    name: str
    status: str
    organizationId: str
    description: Optional[str] = None
    organizationName: Optional[str]
    createdAt: str
    updatedAt: Optional[str] = None
