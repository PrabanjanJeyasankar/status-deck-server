# ---
# File: auth/routes.py
# Purpose: FastAPI routes for user signup, login, and authenticated user retrieval with debug logging
# ---

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from app.utils.hash import hash_password, verify_password
from pydantic import BaseModel, EmailStr
from app.db import db
import logging

# Configure structured logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

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
# Handle user signup with structured logging for debugging 502 issues.
# ---
@router.post("/signup", response_model=LoginResponse)
async def signup(data: SignupRequest):
    try:
        logger.info(f"[SIGNUP] Received signup request for {data.email}")
        org_domain = extract_org_from_email(data.email)
        org = await db.organization.find_unique(where={"domain": org_domain})
        if not org:
            logger.info(f"[SIGNUP] Organization '{org_domain}' not found. Creating new organization.")
            org = await db.organization.create({"domain": org_domain, "name": org_domain})

        existing = await db.user.find_first(where={
            "email": data.email,
            "organizationId": org.id
        })
        if existing:
            logger.warning(f"[SIGNUP] Email {data.email} already exists in organization {org_domain}")
            raise HTTPException(status_code=400, detail="Email already exists in organization")

        hashed = hash_password(data.password)
        user = await db.user.create({
            "email": data.email,
            "hashedPassword": hashed,
            "name": data.name,
            "role": "ADMIN",
            "organizationId": org.id,
        })
        logger.info(f"[SIGNUP] User {data.email} successfully created in organization {org_domain}")

        return LoginResponse(
            user_id=user.id, email=user.email, name=user.name,
            role=user.role, organization_id=org.id, organization_name=org.name
        )
    except Exception as e:
        logger.error(f"[SIGNUP][ERROR] {e}", exc_info=True)
        raise

# ---
# Handle user login with structured logging for debugging 502 issues.
# ---
@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest):
    try:
        logger.info(f"[LOGIN] Received login request for {data.email}")
        org_domain = data.email.split("@")[-1]
        org = await db.organization.find_unique(where={"domain": org_domain})
        if not org:
            logger.warning(f"[LOGIN] Organization '{org_domain}' not found for {data.email}")
            raise HTTPException(status_code=404, detail="Organization not found")

        user = await db.user.find_first(where={
            "email": data.email,
            "organizationId": org.id
        })
        if not user or not verify_password(data.password, user.hashedPassword):
            logger.warning(f"[LOGIN] Invalid credentials for {data.email}")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        logger.info(f"[LOGIN] User {data.email} successfully authenticated")
        return LoginResponse(
            user_id=user.id, email=user.email, name=user.name,
            role=user.role, organization_id=org.id, organization_name=org.name
        )
    except Exception as e:
        logger.error(f"[LOGIN][ERROR] {e}", exc_info=True)
        raise
