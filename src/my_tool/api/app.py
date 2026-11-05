"""Pilot API. Local records never write back to procurement source systems."""
import hashlib
import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from my_tool.core.review import review_request
from my_tool.db.models import Audit, Chunk, Conversation, Document, Handoff, LoginSession, Message, ProcurementRequest, PromptTemplate, RequestVersion, Review, User, now
from my_tool.db.session import engine, get_session, init_db
from my_tool.services.knowledge import answer, cosine, embed, provider_name

@asynccontextmanager
async def lifespan(app):
    await init_db()
    yield
    await engine.dispose()

app = FastAPI(title='科研采购审核与交接助手（试点）', version='0.1.0', lifespan=lifespan)
DB = Annotated[AsyncSession, Depends(get_session)]

async def current_user(db: DB, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Bearer token required')
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    user = await db.scalar(select(User).where(User.token_hash == digest, User.active.is_(True)))
    if not user:
        try:
            from my_tool.services.auth import decode_token
            user_id, session_id = decode_token(authorization[7:])
            token_session = await db.get(LoginSession, session_id)
            user = await db.get(User, user_id) if token_session and token_session.user_id == user_id and token_session.revoked_at is None else None
        except Exception:
            user = None
    if not user or not user.active:
        raise HTTPException(401, '认证失败')
    return user

Actor = Annotated[User, Depends(current_user)]

def require(actor, *roles):
    if actor.role not in roles:
        raise HTTPException(403, 'Insufficient permission')

def audit(db, actor, action, kind, identifier):
    db.add(Audit(actor_id=actor.id, action=action, object_type=kind, object_id=str(identifier)))

async def save(db):
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Duplicate or invalid record')

async def visible_request(db, actor, request_id):
    record = await db.get(ProcurementRequest, request_id)
    if not record or (record.owner_id != actor.id and actor.role not in {'reviewer', 'safety'}):
        raise HTTPException(404, 'Request not found')
    return record

async def visible_version(db, actor, version_id):
    version = await db.get(RequestVersion, version_id)
    if not version:
        raise HTTPException(404, 'Version not found')
    await visible_request(db, actor, version.request_id)
    return version

class RequestInput(BaseModel):
    business_id: str = Field(min_length=1, max_length=100, pattern=r'.*\S.*')
    version: str = Field(min_length=1, max_length=40, pattern=r'.*\S.*')
    cas: str = Field(min_length=1, max_length=100, pattern=r'.*\S.*')
    concentration: str = Field(min_length=1, max_length=100, pattern=r'.*\S.*')
    package: str = Field(min_length=1, max_length=100, pattern=r'.*\S.*')
    cold_chain: bool = False
    temperature_log_present: bool = False
    hazardous: bool = False
    safety_approval_present: bool = False
    budget_approval_present: bool = False

class CatalogItem(BaseModel):
    cas: str = Field(min_length=1)
    concentration: str = Field(min_length=1)
    package: str = Field(min_length=1)
    updated_at: str
    sku: str = ''

class ReviewInput(BaseModel):
    catalog: list[CatalogItem] = Field(max_length=1000)
    as_of: date
    max_catalog_age_days: int = Field(default=30, ge=0, le=3650)

class DecisionInput(BaseModel):
    decision: str = Field(pattern='^(accepted|rejected|needs_correction)$')
    comment: str = Field(min_length=1, max_length=2000)

class HandoffInput(BaseModel):
    version_id: int
    receiver_id: int
    unresolved: str = Field(default='', max_length=2000)

class DocumentInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=40)
    source: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=2, max_length=50000)

class QuestionInput(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: int | None = None

@app.get('/health')
async def health():
    return {'status': 'ok', 'mode': 'pilot'}

@app.get('/me')
async def me(actor: Actor):
    return {'id': actor.id, 'username': actor.username, 'role': actor.role}

@app.get('/users')
async def list_business_users(actor: Actor, db: DB):
    users = (await db.scalars(select(User).where(User.active.is_(True), User.role.in_(['applicant', 'reviewer', 'safety'])).order_by(User.id))).all()
    audit(db, actor, 'list', 'users', 'business')
    await save(db)
    return [{'id': u.id, 'username': u.username, 'role': u.role} for u in users]

@app.get('/requests')
async def list_requests(actor: Actor, db: DB):
    query = select(ProcurementRequest).order_by(ProcurementRequest.id.desc()).limit(100)
    if actor.role not in {'reviewer', 'safety'}:
        query = query.where(ProcurementRequest.owner_id == actor.id)
    records = (await db.scalars(query)).all()
    audit(db, actor, 'list', 'request', 'visible')
    await save(db)
    return [{'id': r.id, 'business_id': r.business_id, 'owner_id': r.owner_id, 'created_at': r.created_at} for r in records]

@app.get('/versions/{version_id}/reviews')
async def list_reviews(version_id: int, actor: Actor, db: DB):
    await visible_version(db, actor, version_id)
    reviews = (await db.scalars(select(Review).where(Review.version_id == version_id).order_by(Review.id.desc()))).all()
    audit(db, actor, 'list', 'review', version_id)
    await save(db)
    return [{'id': r.id, 'result': r.result, 'decision': r.decision, 'reviewer_id': r.reviewer_id, 'comment': r.comment} for r in reviews]

@app.get('/handoffs')
async def list_handoffs(actor: Actor, db: DB):
    from sqlalchemy import or_
    query = select(Handoff).order_by(Handoff.id.desc()).limit(100)
    if actor.role not in {'reviewer', 'safety'}:
        query = query.where(or_(Handoff.sender_id == actor.id, Handoff.receiver_id == actor.id))
    items = (await db.scalars(query)).all()
    audit(db, actor, 'list', 'handoff', 'visible')
    await save(db)
    return [{'id': h.id, 'version_id': h.version_id, 'sender_id': h.sender_id, 'receiver_id': h.receiver_id, 'unresolved': h.unresolved, 'status': 'confirmed' if h.confirmed_at else 'pending'} for h in items]

@app.post('/requests', status_code=201)
async def create_request(data: RequestInput, actor: Actor, db: DB):
    require(actor, 'applicant', 'reviewer')
    record = ProcurementRequest(business_id=data.business_id, owner_id=actor.id)
    db.add(record)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Business ID already exists')
    version = RequestVersion(request_id=record.id, version=data.version, payload=data.model_dump())
    db.add(version)
    await db.flush()
    audit(db, actor, 'create', 'request_version', version.id)
    await save(db)
    return {'request_id': record.id, 'version_id': version.id}

@app.post('/requests/{request_id}/versions', status_code=201)
async def create_version(request_id: int, data: RequestInput, actor: Actor, db: DB):
    record = await visible_request(db, actor, request_id)
    if actor.id != record.owner_id:
        raise HTTPException(403, 'Only the owner may add a version')
    # PostgreSQL 下与草稿确认共用申请行锁，避免确认时版本并发变化。
    await db.scalar(select(ProcurementRequest).where(ProcurementRequest.id == record.id).with_for_update())
    if data.business_id != record.business_id:
        raise HTTPException(422, 'Business ID cannot change')
    version = RequestVersion(request_id=record.id, version=data.version, payload=data.model_dump())
    db.add(version)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Version already exists')
    audit(db, actor, 'create', 'request_version', version.id)
    await save(db)
    return {'request_id': record.id, 'version_id': version.id}

@app.get('/requests/{request_id}')
async def get_request(request_id: int, actor: Actor, db: DB):
    record = await visible_request(db, actor, request_id)
    versions = (await db.scalars(select(RequestVersion).where(RequestVersion.request_id == record.id).order_by(RequestVersion.id))).all()
    audit(db, actor, 'read', 'request', record.id)
    await save(db)
    return {'id': record.id, 'business_id': record.business_id, 'owner_id': record.owner_id, 'versions': [{'id': v.id, 'version': v.version, 'payload': v.payload} for v in versions]}

@app.post('/versions/{version_id}/reviews', status_code=201)
async def run_review(version_id: int, data: ReviewInput, actor: Actor, db: DB):
    version = await visible_version(db, actor, version_id)
    handoff = await db.scalar(select(Handoff).where(Handoff.version_id == version.id).order_by(Handoff.id.desc()))
    payload = dict(version.payload)
    payload['handoff_receiver'] = str(handoff.receiver_id) if handoff else ''
    payload['handoff_confirmed'] = bool(handoff and handoff.confirmed_at)
    catalog = [item.model_dump() for item in data.catalog]
    result = review_request(payload, catalog, as_of=data.as_of, max_catalog_age_days=data.max_catalog_age_days)
    result['max_catalog_age_days'] = data.max_catalog_age_days
    review = Review(version_id=version.id, result=result, catalog_snapshot=catalog, as_of=data.as_of.isoformat())
    db.add(review)
    await db.flush()
    audit(db, actor, 'run_review', 'review', review.id)
    await save(db)
    return {'id': review.id, **result}

@app.get('/reviews/{review_id}')
async def get_review(review_id: int, actor: Actor, db: DB):
    review = await db.get(Review, review_id)
    if not review:
        raise HTTPException(404, 'Review not found')
    await visible_version(db, actor, review.version_id)
    audit(db, actor, 'read', 'review', review.id)
    await save(db)
    return {'id': review.id, 'version_id': review.version_id, 'result': review.result, 'as_of': review.as_of, 'rule_version': review.rule_version, 'reviewer_id': review.reviewer_id, 'decision': review.decision, 'comment': review.comment}

@app.post('/reviews/{review_id}/decision')
async def decide(review_id: int, data: DecisionInput, actor: Actor, db: DB):
    require(actor, 'reviewer')
    review = await db.get(Review, review_id)
    if not review:
        raise HTTPException(404, 'Review not found')
    if review.decision is not None:
        raise HTTPException(409, 'Review already has a decision; run a new review')
    review.reviewer_id, review.decision, review.comment = actor.id, data.decision, data.comment
    audit(db, actor, 'human_decision', 'review', review.id)
    await save(db)
    return {'id': review.id, 'decision': review.decision, 'approved': False}

@app.post('/handoffs', status_code=201)
async def create_handoff(data: HandoffInput, actor: Actor, db: DB):
    await visible_version(db, actor, data.version_id)
    receiver = await db.get(User, data.receiver_id)
    if not receiver or not receiver.active or receiver.id == actor.id or receiver.role not in {'applicant', 'reviewer', 'safety'}:
        raise HTTPException(422, 'Receiver must be another active business user')
    handoff = Handoff(version_id=data.version_id, sender_id=actor.id, receiver_id=receiver.id, unresolved=data.unresolved)
    db.add(handoff)
    await db.flush()
    audit(db, actor, 'create', 'handoff', handoff.id)
    await save(db)
    return {'id': handoff.id, 'status': 'pending', 'receiver_id': receiver.id}

@app.get('/handoffs/{handoff_id}')
async def get_handoff(handoff_id: int, actor: Actor, db: DB):
    item = await db.get(Handoff, handoff_id)
    if not item or (actor.id not in {item.sender_id, item.receiver_id} and actor.role not in {'reviewer', 'safety'}):
        raise HTTPException(404, 'Handoff not found')
    audit(db, actor, 'read', 'handoff', item.id)
    await save(db)
    return {'id': item.id, 'version_id': item.version_id, 'sender_id': item.sender_id, 'receiver_id': item.receiver_id, 'unresolved': item.unresolved, 'status': 'confirmed' if item.confirmed_at else 'pending', 'confirmed_at': item.confirmed_at}

@app.post('/handoffs/{handoff_id}/confirm')
async def confirm_handoff(handoff_id: int, actor: Actor, db: DB):
    item = await db.get(Handoff, handoff_id)
    if not item:
        raise HTTPException(404, 'Handoff not found')
    if actor.id != item.receiver_id:
        raise HTTPException(403, 'Only the designated receiver may confirm')
    if item.confirmed_at:
        raise HTTPException(409, 'Handoff already confirmed')
    item.confirmed_at = now()
    audit(db, actor, 'confirm', 'handoff', item.id)
    await save(db)
    return {'id': item.id, 'status': 'confirmed', 'confirmed_at': item.confirmed_at}

@app.post('/documents', status_code=201)
async def create_document(data: DocumentInput, actor: Actor, db: DB):
    require(actor, 'admin')
    paragraphs = [p.strip() for p in data.content.split('\n') if p.strip()]
    if not paragraphs or any(len(p) > 2000 for p in paragraphs):
        raise HTTPException(422, 'Content must contain paragraphs of at most 2000 characters')
    vectors = [await embed(p) for p in paragraphs]
    doc = Document(title=data.title, version=data.version, source=data.source, created_by=actor.id)
    db.add(doc)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Document version already exists')
    for i, (paragraph, vector) in enumerate(zip(paragraphs, vectors), 1):
        db.add(Chunk(document_id=doc.id, position=i, content=paragraph, embedding=vector, embedding_model=provider_name()))
    audit(db, actor, 'create', 'document', doc.id)
    await save(db)
    return {'id': doc.id, 'chunks': len(paragraphs), 'embedding_model': provider_name()}

@app.post('/documents/{document_id}/retire')
async def retire_document(document_id: int, actor: Actor, db: DB):
    require(actor, 'admin')
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, 'Document not found')
    doc.status = 'retired'
    audit(db, actor, 'retire', 'document', doc.id)
    await save(db)
    return {'id': doc.id, 'status': doc.status}

@app.get('/documents')
async def list_documents(actor: Actor, db: DB):
    require(actor, 'admin')
    docs = (await db.scalars(select(Document).order_by(Document.id))).all()
    audit(db, actor, 'list', 'document', 'all')
    await save(db)
    return [{'id': d.id, 'title': d.title, 'version': d.version, 'source': d.source, 'status': d.status} for d in docs]

@app.post('/questions')
async def ask(data: QuestionInput, actor: Actor, db: DB):
    if data.conversation_id:
        conversation = await db.get(Conversation, data.conversation_id)
        if not conversation or conversation.owner_id != actor.id:
            raise HTTPException(404, 'Conversation not found')
    else:
        conversation = Conversation(owner_id=actor.id)
        db.add(conversation)
        await db.flush()
    vector = await embed(data.question)
    rows = (await db.execute(select(Chunk, Document).join(Document).where(Document.status == 'active', Chunk.embedding_model == provider_name()))).all()
    ranked = sorted(((cosine(vector, c.embedding), c, d) for c, d in rows), key=lambda x: x[0], reverse=True)
    citations = [{'document_id': d.id, 'title': d.title, 'version': d.version, 'source': d.source, 'paragraph': c.position, 'content': c.content} for score, c, d in ranked[:3] if score >= 0.25]
    template = await db.scalar(select(PromptTemplate).order_by(PromptTemplate.id.desc()).limit(1))
    result = await answer(data.question, citations, template.content if template else None)
    db.add_all([Message(conversation_id=conversation.id, role='user', content=data.question, citations=[]), Message(conversation_id=conversation.id, role='assistant', content=result, citations=citations)])
    audit(db, actor, 'ask', 'conversation', conversation.id)
    await save(db)
    return {'conversation_id': conversation.id, 'answer': result, 'citations': citations}

@app.get('/conversations/{conversation_id}')
async def get_conversation(conversation_id: int, actor: Actor, db: DB):
    conversation = await db.get(Conversation, conversation_id)
    if not conversation or conversation.owner_id != actor.id:
        raise HTTPException(404, 'Conversation not found')
    messages = (await db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id))).all()
    audit(db, actor, 'read', 'conversation', conversation.id)
    await save(db)
    return {'id': conversation.id, 'messages': [{'role': m.role, 'content': m.content, 'citations': m.citations} for m in messages]}


# 页面与流式聊天路由复用本模块的认证依赖。
from my_tool.api.chat import router as chat_router
app.include_router(chat_router)

from my_tool.api.admin import router as admin_router
app.include_router(admin_router)

from my_tool.api.agent import router as agent_router
app.include_router(agent_router)
