"""启动仅供本机演示的科研采购制度聊天页面。"""
import asyncio
import hashlib
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
# 使用独立目录和数据库，避免覆盖现有数据；演示模式不调用外部模型。
demo_dir = ROOT / '.local_demo'
demo_dir.mkdir(exist_ok=True)
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///' + (demo_dir / 'demo.db').as_posix()
os.environ['EMBEDDING_MODEL'] = 'local-hash-v1'
os.environ.pop('CHAT_MODEL', None)
os.environ.pop('AGENT_MODEL', None)
secret_file = demo_dir / 'jwt-secret.txt'
if not secret_file.exists():
    secret_file.write_text(secrets.token_urlsafe(48), encoding='utf-8')
os.environ['PILOT_JWT_SECRET'] = secret_file.read_text(encoding='utf-8')
from sqlalchemy import select
from my_tool.db.models import Chunk, Document, PasswordAccount, User
from my_tool.db.session import Session, engine, init_db
from my_tool.services.knowledge import embed
from my_tool.services.auth import hash_password
import uvicorn

async def seed_demo():
    await init_db()
    token_file = demo_dir / 'access-token.txt'
    async with Session() as db:
        user = await db.scalar(select(User).where(User.username == 'local-demo'))
        if user and not token_file.exists():
            raise RuntimeError('演示令牌文件丢失；请先移走现有演示数据库再重新初始化。')
        if user is None:
            token = secrets.token_urlsafe(32)
            token_file.write_text(token, encoding='utf-8')
            user = User(username='local-demo', role='applicant', token_hash=hashlib.sha256(token.encode()).hexdigest())
            db.add(user)
            await db.flush()
        # 单独的演示管理员，密码只保存在本地忽略目录内。
        admin = await db.scalar(select(User).where(User.username == 'demo-admin'))
        password_file = demo_dir / 'admin-password.txt'
        if admin and not password_file.exists():
            raise RuntimeError('演示管理员密码文件丢失，请检查本地演示目录。')
        if admin is None:
            password = secrets.token_urlsafe(18)
            password_file.write_text(password, encoding='utf-8')
            admin = User(username='demo-admin', role='admin', token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest())
            db.add(admin)
            await db.flush()
            db.add(PasswordAccount(user_id=admin.id, password_hash=hash_password(password)))
        doc = await db.scalar(select(Document).where(Document.title == '模拟科研采购制度'))
        if doc is None:
            doc = Document(title='模拟科研采购制度', version='demo-v1', source='data/sample_procurement_policy.md', created_by=user.id)
            db.add(doc)
            await db.flush()
            text = (ROOT / 'data' / 'sample_procurement_policy.md').read_text(encoding='utf-8-sig')
            paragraphs = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith('#')]
            for i, paragraph in enumerate(paragraphs, 1):
                db.add(Chunk(document_id=doc.id, position=i, content=paragraph, embedding_model='local-hash-v1', embedding=await embed(paragraph)))
        await db.commit()
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(seed_demo())
    print('演示页面：http://127.0.0.1:8765/chat-ui')
    print('演示令牌保存在 .local_demo/access-token.txt')
    print('管理后台：http://127.0.0.1:8765/admin-ui；账号 demo-admin，密码在 .local_demo/admin-password.txt')
    uvicorn.run('my_tool.api.app:app', host='127.0.0.1', port=8765, log_level='warning')
