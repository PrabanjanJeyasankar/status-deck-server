import asyncio
from prisma import Prisma
from app.utils.hash import hash_password

async def main():
    db = Prisma()
    await db.connect()

    # 1. Ensure organization exists (by domain, for multi-tenant)
    org_domain = "achme.ai"
    org_name = "Achme"

    org = await db.organization.find_unique(where={"domain": org_domain})
    if not org:
        org = await db.organization.create({
            "name": org_name,
            "domain": org_domain,
        })
        print(f"Organization created: {org.name} ({org.id})")
    else:
        print(f"Organization already exists: {org.name} ({org.id})")

    # 2. Remove admin and user if they exist (idempotent)
    admin_email = "admin@achme.ai"
    user_email = "user@achme.ai"
    for email in [admin_email, user_email]:
        old = await db.user.find_first(where={
            "email": email,
            "organizationId": org.id,
        })
        if old:
            await db.user.delete(where={"id": old.id})
            print(f"Deleted old user: {email}")

    # 3. Create fresh users (admin & user)
    admin = await db.user.create({
        "email": admin_email,
        "hashedPassword": hash_password("12121212"),
        "name": "Admin",
        "role": "ADMIN",
        "organizationId": org.id,
    })
    print(f"Admin user created: {admin.email}")

    user = await db.user.create({
        "email": user_email,
        "hashedPassword": hash_password("12121212"),
        "name": "User",
        "role": "USER",
        "organizationId": org.id,
    })
    print(f"Normal user created: {user.email}")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
