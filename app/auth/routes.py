# ---
# File: auth/routes.py
# Purpose: FastAPI routes for user signup, login, and authenticated user retrieval
# ---

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from app.utils.hash import hash_password, verify_password
from pydantic import BaseModel, EmailStr
from app.db import db

router = APIRouter()
security = HTTPBasic()

# Data model for signup requests with user name, email, and password
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

# Data model for login requests with user email and password
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# Data model for login responses returned to the client after signup/login
class LoginResponse(BaseModel):
    user_id: str
    email: EmailStr
    name: str
    role: str
    organization_id: str
    organization_name: str

# ---
# Utility function to extract the organization domain from an email address.
# Used for auto-linking users to their organization based on email domain.
# ---
def extract_org_from_email(email: str) -> str:
    return email.split("@")[-1].lower().strip()

# ---
# Handle user signup.
# Creates the organization if it does not exist based on email domain,
# checks for existing user in that organization,
# hashes the password, creates the user,
# and returns user and organization details for the session.
# ---
@router.post("/api/signup", response_model=LoginResponse)
async def signup(data: SignupRequest):
    org_domain = extract_org_from_email(data.email)
    org = await db.organization.find_unique(where={"domain": org_domain})
    if not org:
        org = await db.organization.create({"domain": org_domain, "name": org_domain})
    existing = await db.user.find_first(where={
        "email": data.email,
        "organizationId": org.id
    })
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists in organization")
    hashed = hash_password(data.password)
    user = await db.user.create({
        "email": data.email,
        "hashedPassword": hashed,
        "name": data.name,
        "role": "ADMIN",
        "organizationId": org.id,
    })
    return LoginResponse(
        user_id=user.id, email=user.email, name=user.name,
        role=user.role, organization_id=org.id, organization_name=org.name
    )

# ---
# Handle user login.
# Verifies the organization exists based on email domain,
# fetches the user by email and organization,
# checks the password, and returns user and organization details on success.
# ---
@router.post("/api/login", response_model=LoginResponse)
async def login(data: LoginRequest):
    org_domain = data.email.split("@")[-1]
    org = await db.organization.find_unique(where={"domain": org_domain})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    user = await db.user.find_first(where={
        "email": data.email,
        "organizationId": org.id
    })
    if not user or not verify_password(data.password, user.hashedPassword):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(
        user_id=user.id, email=user.email, name=user.name,
        role=user.role, organization_id=org.id, organization_name=org.name
    )

