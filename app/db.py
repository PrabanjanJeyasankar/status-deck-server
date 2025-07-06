# ---
# File: app/db.py
# Purpose: Initializes and exposes a Prisma client instance for database operations
# ---

from prisma import Prisma

# Initialize the Prisma client for database operations
db = Prisma()
