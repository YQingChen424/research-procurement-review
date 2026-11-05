"""由本机管理员通过环境变量创建试点用户名和密码。"""
import asyncio
import hashlib
import os
import secrets
from sqlalchemy import select
from my_tool.db.models import PasswordAccount, User
from my_tool.db.session import Session, engine, init_db
from my_tool.services.auth import hash_password

async def main():
    username = os.environ['PILOT_USERNAME'].strip()
    role = os.environ['PILOT_ROLE']
    password_hash = hash_password(os.environ['PILOT_PASSWORD'])
    if not username or role not in {'applicant', 'reviewer', 'safety', 'admin'}:
        raise ValueError('账号或角色无效')
    await init_db()
    async with Session() as db:
        user = await db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username, role=role, token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest())
            db.add(user)
            await db.flush()
        else:
            user.role = role
        account = await db.get(PasswordAccount, user.id)
        if account is None:
            db.add(PasswordAccount(user_id=user.id, password_hash=password_hash))
        else:
            account.password_hash = password_hash
        await db.commit()
    await engine.dispose()
    print('试点账号已保存。')

if __name__ == '__main__':
    asyncio.run(main())
