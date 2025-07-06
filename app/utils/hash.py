# ---
# File: utils/hash.py
# Purpose: Password hashing and verification utilities using bcrypt
# ---

from passlib.context import CryptContext

# Initialize the password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---
# Hash a plain text password using bcrypt.
# Returns the hashed password as a string for secure storage.
# ---
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# ---
# Verify a plain text password against a previously hashed password.
# Returns True if the password matches, False otherwise.
# ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
