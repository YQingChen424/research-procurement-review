"""Async database setup. Schema creation is intended only for the pilot."""
import os
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from my_tool.db.models import Base

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./pilot.db')
engine = create_async_engine(DATABASE_URL)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine.sync_engine, 'connect')
    def enable_sqlite_foreign_keys(connection, _):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
Session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as connection:
        if connection.dialect.name == 'postgresql':
            from sqlalchemy import text
            await connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        await connection.run_sync(Base.metadata.create_all)

async def get_session():
    async with Session() as session:
        yield session
