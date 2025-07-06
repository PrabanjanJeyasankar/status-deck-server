# incidents/models.py

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from enum import Enum

class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    MONITORING = "MONITORING"

class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class IncidentUpdateCreate(BaseModel):
    message: str
    createdBy: Optional[str] = None

class IncidentUpdateRead(BaseModel):
    id: str
    message: str
    createdAt: datetime
    createdBy: Optional[str]

    class Config:
        orm_mode = True

class IncidentCreate(BaseModel):
    organizationId: str
    title: str
    description: Optional[str] = None
    severity: IncidentSeverity
    affectedServiceIds: List[str]
    monitorId: Optional[str] = None
    autoCreated: bool = False
    createdByUserId: Optional[str] = None

class IncidentUpdate(BaseModel):
    status: Optional[IncidentStatus] = None
    resolvedAt: Optional[datetime] = None
    description: Optional[str] = None

class IncidentRead(BaseModel):
    id: str
    organizationId: str
    title: str
    description: Optional[str]
    status: IncidentStatus
    severity: IncidentSeverity
    autoCreated: bool
    monitorId: Optional[str]
    affectedServiceIds: List[str]
    createdAt: datetime
    updatedAt: datetime
    resolvedAt: Optional[datetime]
    createdByUserId: Optional[str]
    updates: List[IncidentUpdateRead] = []
    autoResolved: Optional[bool] = False

    class Config:
        orm_mode = True
