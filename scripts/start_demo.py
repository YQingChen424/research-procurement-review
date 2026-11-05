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
from sqlalchemy import select
from my_tool.db.models import Chunk, Document, User
from my_tool.db.session import Session, engine, init_db
from my_tool.services.knowledge import embed
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
    uvicorn.run('my_tool.api.app:app', host='127.0.0.1', port=8765, log_level='warning')
