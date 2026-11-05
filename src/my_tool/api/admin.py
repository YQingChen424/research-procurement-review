"""试点管理后台：登录、制度上传、提示词与经授权的审计。"""
import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sqlalchemy import delete, func, select
from my_tool.api.app import Actor, DB, audit, require, save
from my_tool.db.models import Chunk, Conversation, Document, LoginAttempt, LoginSession, Message, MessageFlag, PasswordAccount, PromptTemplate, User, now
from my_tool.services.auth import decode_token, issue_token, verify_password
from my_tool.services.knowledge import embed, provider_name

router = APIRouter()

class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)

class PromptInput(BaseModel):
    content: str = Field(min_length=2, max_length=5000)

class FlagInput(BaseModel):
    reason: str = Field(min_length=2, max_length=2000)

@router.get('/admin-ui', include_in_schema=False)
async def admin_ui():
    return FileResponse(Path(__file__).resolve().parent / 'admin.html')

@router.post('/auth/login')
async def login(data: LoginInput, request: Request, db: DB):
    # 使用服务器接收的客户端地址和账号哈希限速，不信任客户端提供的转发头。
    address = request.client.host if request.client else 'unknown'
    attempt_key = hashlib.sha256((address + '\0' + data.username.casefold()).encode()).hexdigest()
    recent = await db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key_hash == attempt_key, LoginAttempt.created_at >= now() - timedelta(minutes=10)))
    if recent >= 5:
        raise HTTPException(429, detail={'code':'LOGIN_RATE_LIMIT','message':'登录尝试过多，请十分钟后重试'})
    user = await db.scalar(select(User).where(User.username == data.username, User.active.is_(True)))
    account = await db.get(PasswordAccount, user.id) if user else None
    if not account or not await asyncio.to_thread(verify_password, data.password, account.password_hash):
        db.add(LoginAttempt(key_hash=attempt_key))
        await db.commit()
        raise HTTPException(401, detail={'code':'LOGIN_FAILED','message':'账号或密码错误'})
    session_id = secrets.token_urlsafe(32)
    try:
        token = issue_token(user.id, session_id)
    except RuntimeError:
        raise HTTPException(503, detail={'code':'AUTH_NOT_CONFIGURED','message':'登录服务尚未配置'})
    await db.execute(delete(LoginAttempt).where(LoginAttempt.key_hash == attempt_key))
    db.add(LoginSession(id=session_id, user_id=user.id))
    audit(db, user, 'login', 'user', user.id)
    await save(db)
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': 1800, 'role': user.role}

@router.post('/auth/logout')
async def logout(actor: Actor, db: DB, authorization: str = Header(...)):
    try:
        user_id, session_id = decode_token(authorization[7:])
    except Exception:
        raise HTTPException(400, '仅支持退出 JWT 登录') from None
    item = await db.get(LoginSession, session_id)
    if not item or item.user_id != actor.id or user_id != actor.id:
        raise HTTPException(401, '会话无效')
    item.revoked_at = now()
    audit(db, actor, 'logout', 'user', actor.id)
    await save(db)
    return {'message':'已退出登录'}

def extract_document(filename, content):
    suffix = Path(filename).suffix.lower()
    if suffix == '.md':
        try:
            return content.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ValueError('Markdown 必须为 UTF-8 编码') from None
    if suffix == '.pdf':
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError('暂不支持加密 PDF')
            if len(reader.pages) > 100:
                raise ValueError('PDF 不得超过 100 页')
            return '\n'.join(page.extract_text() or '' for page in reader.pages)
        except ValueError:
            raise
        except Exception:
            raise ValueError('PDF 解析失败') from None
    raise ValueError('仅支持 Markdown 或 PDF 文件')

@router.post('/admin/documents', status_code=201)
async def upload_document(actor: Actor, db: DB, file: UploadFile = File(...), title: str = Form(..., min_length=1, max_length=200), version: str = Form(..., min_length=1, max_length=40)):
    require(actor, 'admin')
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, '文件不得超过 2 MB')
    try:
        text = await asyncio.to_thread(extract_document, file.filename or '', data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if not text.strip():
        raise HTTPException(422, '文档没有可提取的文本')
    parts = [text[i:i+500] for i in range(0, len(text), 500) if text[i:i+500].strip()]
    vectors = [await embed(part) for part in parts]
    doc = Document(title=title, version=version, source=Path(file.filename or '').name, created_by=actor.id)
    db.add(doc)
    try:
        await db.flush()
    except Exception as exc:
        from sqlalchemy.exc import IntegrityError
        if isinstance(exc, IntegrityError):
            await db.rollback()
            raise HTTPException(409, '文档版本已存在') from None
        raise
    for number, (part, vector) in enumerate(zip(parts, vectors), 1):
        db.add(Chunk(document_id=doc.id, position=number, content=part, embedding=vector, embedding_model=provider_name()))
    audit(db, actor, 'upload', 'document', doc.id)
    await save(db)
    return {'id': doc.id, 'chunks':len(parts), 'status':doc.status}

@router.get('/admin/prompts')
async def get_prompts(actor: Actor, db: DB):
    require(actor, 'admin')
    rows = (await db.scalars(select(PromptTemplate).order_by(PromptTemplate.id.desc()).limit(100))).all()
    return [{'id': p.id, 'content':p.content, 'created_at':p.created_at} for p in rows]

@router.post('/admin/prompts', status_code=201)
async def publish_prompt(data: PromptInput, actor: Actor, db: DB):
    require(actor, 'admin')
    row = PromptTemplate(content=data.content, created_by=actor.id)
    db.add(row)
    await db.flush()
    audit(db, actor, 'publish', 'prompt', row.id)
    await save(db)
    return {'id':row.id, 'content':row.content}

@router.get('/admin/audit/conversations')
async def audit_conversations(actor: Actor, db: DB, user_id: int | None = None, since: datetime | None = None, until: datetime | None = None, limit: int = Query(50, ge=1, le=100)):
    require(actor, 'admin')
    query = select(Message, Conversation, User).join(Conversation, Message.conversation_id == Conversation.id).join(User, Conversation.owner_id == User.id)
    if user_id is not None:
        query = query.where(User.id == user_id)
    if since is not None:
        query = query.where(Message.created_at >= since)
    if until is not None:
        query = query.where(Message.created_at <= until)
    rows = (await db.execute(query.order_by(Message.id.desc()).limit(limit))).all()
    audit(db, actor, 'list', 'audit_conversations', 'filtered')
    await save(db)
    indicators = ('跳过审批', '伪造', '绕过安全', '假装确认')
    return [{'message_id':m.id, 'conversation_id':c.id, 'user_id':u.id, 'username':u.username, 'role':m.role, 'content':m.content, 'created_at':m.created_at, 'needs_review':m.role == 'user' and any(word in m.content for word in indicators)} for m,c,u in rows]

@router.post('/admin/audit/messages/{message_id}/flags', status_code=201)
async def flag_message(message_id: int, data: FlagInput, actor: Actor, db: DB):
    require(actor, 'admin')
    if not await db.get(Message, message_id):
        raise HTTPException(404, '消息不存在')
    item = MessageFlag(message_id=message_id, actor_id=actor.id, reason=data.reason)
    db.add(item)
    await db.flush()
    audit(db, actor, 'flag', 'message', message_id)
    await save(db)
    return {'id':item.id,'message_id':message_id}
