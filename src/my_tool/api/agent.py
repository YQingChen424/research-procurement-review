"""五步以内的工具决策循环：演示规划器和可替换模型规划器。"""
import asyncio
from datetime import date, timedelta
import json
import os
from pathlib import Path
from time import perf_counter

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from my_tool.api.app import Actor, DB, visible_version
from my_tool.api.chat import event
from my_tool.core.review import review_request
from my_tool.db.models import AgentDraft, AgentRun, AgentStep, Chunk, Document, Handoff, ProcurementRequest, RequestVersion, User, now
from my_tool.db.session import Session
from my_tool.services.knowledge import embed, provider_name
from my_tool.services.retrieval import rank_policy_chunks

router = APIRouter()
TOOLS = ['search_policy', 'get_request', 'lookup_catalog', 'review_specification', 'check_evidence', 'prepare_handoff', 'finish']

class AgentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=2, max_length=1000)
    version_id: int | None = None
    receiver_id: int | None = None

class ConfirmInput(BaseModel):
    confirm: bool

async def choose_tool(question, completed, mode, observations):
    """默认使用确定性模拟规划器；配置 AGENT_MODEL 时使用兼容工具调用 API。"""
    model = os.getenv('AGENT_MODEL', '')
    if not model:
        plans = {'policy':['search_policy','finish'], 'spec':['get_request','lookup_catalog','review_specification','finish'], 'evidence':['get_request','check_evidence','finish'],
                 'handoff':['get_request','lookup_catalog','review_specification','check_evidence','prepare_handoff']}
        return plans[mode][min(len(completed), len(plans[mode])-1)]
    base, key = os.getenv('MODEL_API_BASE', '').rstrip('/'), os.getenv('MODEL_API_KEY', '')
    if not base or not key:
        raise RuntimeError('智能体模型未配置')
    # 模型仅选择工具名称，业务编号和接收人始终由经过认证的请求提供。
    tools = [{'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':{},'additionalProperties':False}}} for name,description in [
        ('search_policy','查询制度并引用来源'), ('get_request','读取授权申请'), ('lookup_catalog','只读查询模拟目录'), ('review_specification','确定性规格检查'), ('check_evidence','检查证据声明'), ('prepare_handoff','准备待人工确认的本地交接草稿'), ('finish','停止执行并汇报')]]
    messages = [{'role':'system','content':'你是科研采购助手。只选择一个工具；不得采购审批、付款或选择供应商。交接须先读取申请、核对目录和规格、检查证据，再准备草稿，最终由用户确认。证据不足停止。'}, {'role':'user','content':json.dumps({'question':question,'completed':completed,'tool_results':observations},ensure_ascii=False)}]
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(base+'/chat/completions', headers={'Authorization':'Bearer '+key}, json={'model':model,'messages':messages,'tools':tools,'tool_choice':'required','temperature':0})
        response.raise_for_status()
        name = response.json()['choices'][0]['message']['tool_calls'][0]['function']['name']
    if name not in TOOLS:
        raise ValueError('未知工具')
    return name

@router.post('/agent/run')
async def agent_run(data: AgentInput, actor: Actor, db: DB):
    if data.version_id is not None:
        await visible_version(db, actor, data.version_id)
    if data.receiver_id is not None:
        receiver = await db.get(User, data.receiver_id)
        if not receiver or not receiver.active or receiver.id == actor.id or receiver.role not in {'applicant','reviewer','safety'}:
            raise HTTPException(422, '接收人无效')
    run = AgentRun(actor_id=actor.id)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    run_id, actor_id = run.id, actor.id
    mode = 'policy' if data.version_id is None else ('handoff' if data.receiver_id is not None else ('spec' if any(word in data.question.lower() for word in ('规格', 'cas', '候选')) else 'evidence'))

    async def stream():
        completed, state, observations = [], {}, []
        yield event('status', {'run_id':run_id,'message':'正在执行采购核查'})
        async with Session() as session:
            run_row = await session.get(AgentRun, run_id)
            try:
                for _ in range(5):
                    started = perf_counter()
                    tool = await choose_tool(data.question, completed, mode, observations)
                    result = {}
                    # 所有工具都由服务端验证调用顺序和用户可见性。
                    if tool == 'finish':
                        result = {'message':'流程结束，最终结论须人工复核。'}
                    elif tool == 'search_policy':
                        vector = await embed(data.question)
                        records = (await session.execute(select(Chunk, Document).join(Document).where(Document.status == 'active', Chunk.embedding_model == provider_name()))).all()
                        ranked = await asyncio.to_thread(rank_policy_chunks, data.question, vector, records)
                        result = {'citations':[{'title':d.title,'version':d.version,'paragraph':c.position,'content':c.content} for c,d in ranked], 'message':'请核对引用制度。' if ranked else '制度中未找到相关依据。'}
                    elif tool == 'get_request':
                        if data.version_id is None:
                            raise ValueError('缺少申请版本')
                        version = await session.get(RequestVersion, data.version_id)
                        record = await session.get(ProcurementRequest, version.request_id) if version else None
                        actor_row = await session.get(User, actor_id)
                        if not record or (record.owner_id != actor_id and actor_row.role not in {'reviewer','safety'}):
                            raise ValueError('无权访问申请')
                        state['version'] = version
                        result = {'business_id':record.business_id,'version':version.version,'version_id':version.id}
                    elif tool == 'lookup_catalog':
                        if 'get_request' not in completed:
                            raise ValueError('必须先读取申请')
                        file = Path(__file__).resolve().parents[3] / 'data' / 'sample_requests.json'
                        state['catalog'] = json.loads(file.read_text(encoding='utf-8'))['catalog']
                        result = {'source':'模拟目录','count':len(state['catalog'])}
                    elif tool == 'review_specification':
                        if 'lookup_catalog' not in completed:
                            raise ValueError('必须先读取申请和目录')
                        payload = dict(state['version'].payload)
                        result = review_request(payload, state['catalog'], as_of=date.today())
                        state['review'] = result
                    elif tool == 'check_evidence':
                        if 'get_request' not in completed:
                            raise ValueError('必须先读取申请')
                        payload = state['version'].payload
                        missing = []
                        if not payload.get('budget_approval_present'): missing.append('budget_approval_missing')
                        if payload.get('hazardous') and not payload.get('safety_approval_present'): missing.append('safety_approval_missing')
                        if payload.get('cold_chain') and not payload.get('temperature_log_present'): missing.append('temperature_log_missing')
                        state['missing'] = missing
                        result = {'missing':missing,'message':'这些字段只是申请人声明，须由授权人员核验证据。'}
                    elif tool == 'prepare_handoff':
                        required = {'get_request','lookup_catalog','review_specification','check_evidence'}
                        if not required.issubset(completed) or data.receiver_id is None:
                            raise ValueError('交接草稿必须先完成申请、规格和证据检查')
                        blockers = [r for r in state['review']['reasons'] if r != 'handoff_unconfirmed']
                        if blockers or state['missing']:
                            raise ValueError('存在未解决事项，请转人工处理')
                        latest = await session.scalar(select(RequestVersion.id).where(RequestVersion.request_id == state['version'].request_id).order_by(RequestVersion.id.desc()).limit(1))
                        if latest != data.version_id:
                            raise ValueError('申请版本已更新，请重新核查')
                        draft = AgentDraft(actor_id=actor_id, version_id=data.version_id, receiver_id=data.receiver_id, unresolved='申请人声明的审批与证据须由授权人员核实。', expires_at=now()+timedelta(minutes=15))
                        session.add(draft)
                        await session.flush()
                        result = {'draft_id':draft.id,'version_id':draft.version_id,'receiver_id':draft.receiver_id,'unresolved':draft.unresolved,'status':'等待发起人确认','expires_at':draft.expires_at.isoformat()}
                    else:
                        raise ValueError('未知工具')
                    elapsed = int((perf_counter()-started)*1000)
                    session.add(AgentStep(run_id=run_id,tool=tool,parameters={'has_version':data.version_id is not None,'has_receiver':data.receiver_id is not None},elapsed_ms=elapsed,result_summary='已执行' if tool != 'finish' else '结束'))
                    completed.append(tool)
                    observations.append({'tool':tool, 'result':result})
                    await session.commit()
                    yield event('tool', {'tool':tool,'result':result})
                    if tool == 'prepare_handoff':
                        run_row.status = 'awaiting_confirmation'
                        await session.commit()
                        yield event('confirmation_required', result)
                        return
                    if tool == 'finish':
                        run_row.status = 'completed'
                        await session.commit()
                        yield event('done', {'run_id':run_id})
                        return
                run_row.status = 'step_limit'
                await session.commit()
                yield event('done', {'run_id':run_id,'message':'达到五轮上限，转人工处理。'})
            except Exception as exc:
                await session.rollback()
                run_row = await session.get(AgentRun, run_id)
                run_row.status = 'needs_human'
                session.add(AgentStep(run_id=run_id,tool=tool if 'tool' in locals() else 'planner',parameters={},elapsed_ms=0,result_summary='失败或需人工处理'))
                await session.commit()
                yield event('error', {'code':'NEEDS_HUMAN','message':str(exc) if isinstance(exc,ValueError) else '模型或工具不可用，请转人工处理。'})
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})

@router.post('/agent/drafts/{draft_id}/confirm')
async def confirm_draft(draft_id: int, data: ConfirmInput, actor: Actor, db: DB):
    if not data.confirm:
        raise HTTPException(422, '需要明确确认草稿')
    draft = await db.get(AgentDraft, draft_id)
    if not draft or draft.actor_id != actor.id:
        raise HTTPException(404, '草稿不存在')
    version = await visible_version(db, actor, draft.version_id)
    receiver = await db.get(User, draft.receiver_id)
    if not receiver or not receiver.active or receiver.id == actor.id or receiver.role not in {'applicant','reviewer','safety'}:
        raise HTTPException(409, '接收人当前不可用')
    # 与创建新版本共用申请行锁；原有接收人确认仍然是独立步骤。
    await db.scalar(select(ProcurementRequest).where(ProcurementRequest.id == version.request_id).with_for_update())
    latest = await db.scalar(select(RequestVersion.id).where(RequestVersion.request_id == version.request_id).order_by(RequestVersion.id.desc()).limit(1))
    if latest != draft.version_id:
        raise HTTPException(409, '申请版本已更新，请重新核查')
    changed = await db.execute(update(AgentDraft).where(AgentDraft.id == draft.id, AgentDraft.status == 'pending', AgentDraft.expires_at > now()).values(status='confirmed').execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        await db.rollback()
        raise HTTPException(409, '草稿已确认或已过期')
    handoff = Handoff(version_id=draft.version_id,sender_id=actor.id,receiver_id=draft.receiver_id,unresolved=draft.unresolved)
    db.add(handoff)
    await db.commit()
    await db.refresh(handoff)
    return {'handoff_id':handoff.id,'status':'pending_receiver_confirmation','approved':False}

@router.get('/agent/runs/{run_id}/steps')
async def agent_steps(run_id: int, actor: Actor, db: DB):
    run = await db.get(AgentRun,run_id)
    if not run or (run.actor_id != actor.id and actor.role != 'admin'):
        raise HTTPException(404, '运行记录不存在')
    steps = (await db.scalars(select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.id))).all()
    return {'id':run.id,'status':run.status,'steps':[{'tool':s.tool,'parameters':s.parameters,'elapsed_ms':s.elapsed_ms,'result_summary':s.result_summary} for s in steps]}
