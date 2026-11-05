"""运行模拟评测，保存真实观测；未实现的多轮能力标为未运行。"""
import argparse
from contextlib import nullcontext
from unittest.mock import patch
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

def main():
    parser = argparse.ArgumentParser(description='使用隔离数据库运行科研采购模拟评测')
    parser.add_argument('--output', type=Path, default=ROOT / 'evaluation' / 'runs' / 'latest.json')
    args = parser.parse_args()
    cases_path = ROOT / 'evaluation' / 'procurement_cases.json'
    cases = json.loads(cases_path.read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='procurement-eval-') as temporary:
        os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///' + (Path(temporary) / 'test.db').as_posix()
        os.environ['EMBEDDING_MODEL'] = 'local-hash-v1'
        os.environ.pop('AGENT_MODEL', None)
        os.environ.pop('CHAT_MODEL', None)
        from fastapi.testclient import TestClient
        from my_tool.api.app import app
        from my_tool.db.models import Chunk, Document, User
        from my_tool.db.session import Session
        from my_tool.services.knowledge import embed
        async def seed():
            async with Session() as db:
                actor = User(username='eval-applicant',role='applicant',token_hash=hashlib.sha256(b'evaluation-token').hexdigest())
                receiver = User(username='eval-reviewer',role='reviewer',token_hash=hashlib.sha256(b'evaluation-reviewer').hexdigest())
                db.add_all([actor,receiver]); await db.flush()
                doc = Document(title='模拟制度',version='v1',source='sample_procurement_policy.md',created_by=actor.id)
                db.add(doc); await db.flush()
                policy=(ROOT/'data'/'sample_procurement_policy.md').read_text(encoding='utf-8-sig')
                lines=[line.strip() for line in policy.splitlines() if line.strip() and not line.startswith('#')]
                for i,text in enumerate(lines,1):
                    db.add(Chunk(document_id=doc.id,position=i,content=text,embedding_model='local-hash-v1',embedding=await embed(text)))
                await db.commit()
                return receiver.id
        headers={'Authorization':'Bearer evaluation-token'}
        outcomes=[]
        with TestClient(app) as client:
            receiver_id=client.portal.call(seed)
            payload={'business_id':'EVAL-1','version':'v1','cas':'64-17-5','concentration':'70%','package':'500 mL','budget_approval_present':True}
            created=client.post('/requests',json=payload,headers=headers)
            created.raise_for_status()
            version_id=created.json()['version_id']
            for number,case in enumerate(cases,1):
                result={'id':number,'category':case['category'],'question':case['question'],'expected_tools':case['expected_tools'],'expected_behavior':case['expected_behavior']}
                if isinstance(case['question'],list):
                    # 多轮使用现有聊天接口；记录原始结果，是否解对指代需人工评审。
                    session_id = None
                    turns = []
                    try:
                        for question in case['question']:
                            response = client.post('/chat',json={'question':question,'session_id':session_id},headers=headers,timeout=30)
                            response.raise_for_status()
                            events = []
                            for block in response.text.split('\n\n'):
                                lines = block.splitlines()
                                kind = next((line[7:] for line in lines if line.startswith('event: ')),None)
                                data = next((line[6:] for line in lines if line.startswith('data: ')),None)
                                if kind and data: events.append({'event':kind,'data':json.loads(data)})
                            session_id = next(item['data']['session_id'] for item in events if item['event']=='status')
                            turns.append({'question':question,'events':events})
                        result.update(status='needs_manual_review',mode='chat_local_extract',turns=turns)
                    except (httpx.HTTPError,ValueError,StopIteration) as exc:
                        result.update(status='error',error=type(exc).__name__)
                    outcomes.append(result); continue
                request={'question':case['question']}
                if case['category']=='工具' and 'get_request' in case['expected_tools']:
                    request['version_id']=version_id
                    if case['question'] in {'找不到 CAS 的申请如何审核','冷链记录缺失的申请可以通过吗','申请版本变化后继续之前的交接'}:
                        fixture = dict(payload, business_id='EVAL-'+str(number))
                        if case['question'] == '找不到 CAS 的申请如何审核': fixture['cas'] = '000-00-0'
                        if case['question'] == '冷链记录缺失的申请可以通过吗': fixture.update(cold_chain=True,temperature_log_present=False)
                        item = client.post('/requests',json=fixture,headers=headers); item.raise_for_status()
                        request['version_id'] = item.json()['version_id']
                        if case['question'] == '申请版本变化后继续之前的交接':
                            updated = client.post(f"/requests/{item.json()['request_id']}/versions",json=dict(fixture,version='v2'),headers=headers); updated.raise_for_status()
                            request['receiver_id'] = receiver_id
                    if 'prepare_handoff' in case['expected_tools']:
                        request['receiver_id']=receiver_id
                try:
                    # 重复目录仅在本次请求中注入，不修改项目文件或业务数据。
                    catalog_item={'cas':'64-17-5','concentration':'70%','package':'500 mL','updated_at':date.today().isoformat(),'sku':'synthetic-a'}
                    fixture_patch=patch('my_tool.api.agent.load_catalog',return_value=[catalog_item,dict(catalog_item,sku='synthetic-b')]) if case['question']=='目录有两个相同候选如何处理' else nullcontext()
                    with fixture_patch:
                        response=client.post('/agent/run',json=request,headers=headers,timeout=30)
                    response.raise_for_status()
                    events=[]
                    for block in response.text.split('\n\n'):
                        lines=block.splitlines()
                        kind=next((line[7:] for line in lines if line.startswith('event: ')),None)
                        data=next((line[6:] for line in lines if line.startswith('data: ')),None)
                        if kind and data: events.append({'event':kind,'data':json.loads(data)})
                    observed=[event['data']['tool'] for event in events if event['event']=='tool' and event['data']['tool']!='finish']
                    if case['question'] == '对已确认的 R1 交接记录执行创建':
                        draft = next((e['data']['draft_id'] for e in events if e['event']=='confirmation_required'), None)
                        if draft is not None:
                            confirmation = client.post(f'/agent/drafts/{draft}/confirm',json={'confirm':True},headers=headers)
                            events.append({'event':'test_confirmation','data':{'status_code':confirmation.status_code}})
                            if confirmation.status_code == 200: observed.append('confirm_handoff_creation')
                    result.update(status='needs_manual_review',observed_tools=observed,tool_order_matches=(observed==case['expected_tools']),events=events)
                except (httpx.HTTPError, ValueError) as exc:
                    result.update(status='error',error=type(exc).__name__)
                outcomes.append(result)
    try:
        revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    except (OSError,subprocess.CalledProcessError): revision='unknown'
    dirty=subprocess.run(['git','status','--porcelain'],cwd=ROOT,text=True,capture_output=True).stdout.strip() != ''
    agent_hash=hashlib.sha256((ROOT/'src'/'my_tool'/'api'/'agent.py').read_bytes()).hexdigest()
    report={'created_at':datetime.now(timezone.utc).isoformat(),'git_revision':revision,'git_dirty':dirty,'agent_source_sha256':agent_hash,'data_sha256':hashlib.sha256(cases_path.read_bytes()).hexdigest(),'mode':'local_simulated','automated_tool_order_only':True,'results':outcomes}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('评测报告：',args.output)
    print('已执行：',sum(item['status']=='needs_manual_review' for item in outcomes),'；未运行：',sum(item['status']=='not_run' for item in outcomes),'；错误：',sum(item['status']=='error' for item in outcomes))
    return int(any(item['status']=='error' for item in outcomes))

if __name__=='__main__':
    raise SystemExit(main())
