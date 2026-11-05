"""Create or rotate a pilot API credential via environment variables."""
import asyncio
import hashlib
import os
from sqlalchemy import select
from my_tool.db.models import User
from my_tool.db.session import Session, init_db

async def main():
    username = os.environ['PILOT_USERNAME'].strip()
    role = os.environ['PILOT_ROLE']
    token = os.environ['PILOT_TOKEN']
    if not username or role not in {'applicant', 'reviewer', 'safety', 'admin'} or len(token) < 32:
        raise SystemExit('Require username, valid role and a random token of at least 32 characters')
    await init_db()
    async with Session() as session:
        user = await session.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username, role=role, token_hash=hashlib.sha256(token.encode()).hexdigest())
            session.add(user)
        else:
            user.role = role
            user.token_hash = hashlib.sha256(token.encode()).hexdigest()
            user.active = True
        await session.commit()
    print('Pilot credential saved.')

if __name__ == '__main__':
    asyncio.run(main())
