from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict

class MonitorHeader(BaseModel):
    key: str
    value: str

class MonitorCreateRequest(BaseModel):
    name: str
    url: HttpUrl
    method: str
    interval: int
    type: str  # e.g. "HTTP"
    headers: Optional[List[MonitorHeader]] = None
    active: bool = True
    degradedThreshold: int
    timeout: int

class MonitorUpdateRequest(BaseModel):
    name: Optional[str]
    url: Optional[HttpUrl]
    method: Optional[str]
    interval: Optional[int]
    type: Optional[str]
    headers: Optional[List[MonitorHeader]]
    active: Optional[bool]
    degradedThreshold: Optional[int]
    timeout: Optional[int]

class MonitorResponse(BaseModel):
    id: str
    name: str
    url: str
    method: str
    interval: int
    type: str
    headers: List[Dict[str, str]]
    active: bool
    degradedThreshold: int
    timeout: int
    serviceId: str
    createdAt: str
    updatedAt: str


class MonitorWithServiceResponse(BaseModel):
    id: str
    name: str
    url: str
    method: str
    interval: int
    type: str
    headers: List[dict]
    active: bool
    degradedThreshold: int
    timeout: int
    serviceId: str
    serviceName: str
    createdAt: str
    updatedAt: str
