"""End-to-end pilot checks using fabricated data and a temporary database."""
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
temp = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'sqlite+aiosqlite:///' + (Path(temp.name) / 'test.db').as_posix())
os.environ.pop('CHAT_MODEL', None)
os.environ.pop('EMBEDDING_MODEL', None)
from fastapi.testclient import TestClient
from my_tool.api.app import app
from my_tool.db.models import PasswordAccount, User
from my_tool.services.auth import hash_password
from my_tool.db.session import Session

TOKENS = {'alice': 'a'*40, 'bob': 'b'*40, 'reviewer': 'c'*40, 'admin': 'd'*40}
def auth(name):
    return {'Authorization': 'Bearer ' + TOKENS[name]}

async def seed():
    async with Session() as db:
        for name, role in [('alice','applicant'), ('bob','applicant'), ('reviewer','reviewer'), ('admin','admin')]:
            db.add(User(username=name, role=role, token_hash=hashlib.sha256(TOKENS[name].encode()).hexdigest()))
        await db.flush()
        from sqlalchemy import select
        admin = await db.scalar(select(User).where(User.username == 'admin'))
        db.add(PasswordAccount(user_id=admin.id, password_hash=hash_password('test-password-123')))
        await db.commit()

class PilotFlowTest(unittest.TestCase):
    def test_end_to_end_and_authorization(self):
        with TestClient(app) as client:
            client.portal.call(seed)
            self.assertEqual(client.get('/me').status_code, 401)
            users = {name: client.get('/me', headers=auth(name)).json()['id'] for name in TOKENS}
            payload = {'business_id':'DEMO-1', 'version':'v1', 'cas':'64-17-5', 'concentration':'70%', 'package':'500 mL', 'budget_approval_present':True}
            created = client.post('/requests', json=payload, headers=auth('alice'))
            self.assertEqual(created.status_code, 201, created.text)
            ids = created.json()
            self.assertEqual(client.post('/requests', json=payload, headers=auth('alice')).status_code, 409)
            self.assertEqual(client.get(f"/requests/{ids['request_id']}", headers=auth('bob')).status_code, 404)
            self.assertEqual(client.get(f"/requests/{ids['request_id']}", headers=auth('admin')).status_code, 404)
            review_input = {'as_of':'2026-10-23', 'catalog':[{'cas':'64-17-5','concentration':'70%','package':'500 mL','updated_at':'2026-10-20','sku':'demo'}]}
            first = client.post(f"/versions/{ids['version_id']}/reviews", json=review_input, headers=auth('alice')).json()
            self.assertIn('handoff_unconfirmed', first['reasons'])
            self.assertFalse(first['approved'])
            handoff = client.post('/handoffs', json={'version_id':ids['version_id'], 'receiver_id':users['reviewer'], 'unresolved':'confirm packaging'}, headers=auth('alice')).json()
            self.assertEqual(client.post(f"/handoffs/{handoff['id']}/confirm", headers=auth('alice')).status_code, 403)
            self.assertEqual(client.post(f"/handoffs/{handoff['id']}/confirm", headers=auth('reviewer')).json()['status'], 'confirmed')
            second = client.post(f"/versions/{ids['version_id']}/reviews", json=review_input, headers=auth('alice')).json()
            self.assertEqual(second['status'], 'ready_for_human_review')
            newer = client.post('/handoffs', json={'version_id':ids['version_id'], 'receiver_id':users['reviewer']}, headers=auth('alice')).json()
            pending_review = client.post(f"/versions/{ids['version_id']}/reviews", json=review_input, headers=auth('alice')).json()
            self.assertIn('handoff_unconfirmed', pending_review['reasons'])
            self.assertEqual(client.post(f"/handoffs/{newer['id']}/confirm", headers=auth('reviewer')).status_code, 200)
            self.assertEqual(client.post(f"/reviews/{second['id']}/decision", json={'decision':'accepted','comment':'checked'}, headers=auth('alice')).status_code, 403)
            self.assertFalse(client.post(f"/reviews/{second['id']}/decision", json={'decision':'accepted','comment':'checked'}, headers=auth('reviewer')).json()['approved'])
            doc = {'title':'模拟冷链制度','version':'v1','source':'测试材料','content':'冷链试剂验收应检查温度记录。'}
            self.assertEqual(client.post('/documents', json=doc, headers=auth('alice')).status_code, 403)
            self.assertEqual(client.post('/documents', json=doc, headers=auth('admin')).status_code, 201)
            response = client.post('/questions', json={'question':'冷链试剂验收如何检查温度记录？'}, headers=auth('alice')).json()
            self.assertEqual(response['citations'][0]['version'], 'v1')
            stream = client.post('/chat', json={'question':'冷链试剂验收如何检查温度记录？'}, headers=auth('alice'))
            self.assertEqual(stream.status_code, 200)
            self.assertIn('event: citations', stream.text)
            self.assertIn('温度记录', stream.text)
            self.assertIn('模拟冷链制度', stream.text)
            self.assertIn('event: delta', stream.text)
            self.assertIn('event: done', stream.text)
            import json
            event_data = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]
            chat_id = event_data[0]['session_id']
            history = client.get(f'/conversations/{chat_id}', headers=auth('alice')).json()
            self.assertEqual([m['role'] for m in history['messages']], ['user', 'assistant'])
            self.assertEqual(client.post('/chat', json={'session_id':chat_id, 'question':'继续说'}, headers=auth('bob')).status_code, 404)
            followup = client.post('/chat', json={'session_id':chat_id, 'question':'缺了它怎么办？'}, headers=auth('alice'))
            self.assertIn('温度记录', followup.text)
            self.assertEqual(client.get('/chat-ui').status_code, 200)
            unknown = client.post('/chat', json={'question':'火星宇宙飞船引擎的工作原理是什么？'}, headers=auth('alice'))
            self.assertIn('制度中未找到', unknown.text)
            from unittest.mock import patch
            captured = []
            async def mocked_answer(question, citations, history, template=None):
                captured.append(history)
                yield '模拟回答'
            with patch('my_tool.api.chat.generate_answer', mocked_answer):
                for i in range(7):
                    follow = client.post('/chat', json={'session_id':chat_id, 'question':f'冷链复核问题{i}'}, headers=auth('alice'))
                    self.assertIn('event: done', follow.text)
            self.assertEqual(len(captured[-1]), 12)
            self.assertEqual([row['role'] for row in captured[-1]], ['user', 'assistant'] * 6)
            before_failure = len(client.get(f'/conversations/{chat_id}', headers=auth('alice')).json()['messages'])
            async def failing_answer(question, citations, history, template=None):
                yield '部分回答'
                raise RuntimeError('provider failed')
            with patch('my_tool.api.chat.generate_answer', failing_answer):
                failed = client.post('/chat', json={'session_id':chat_id, 'question':'模拟失败问题'}, headers=auth('alice'))
            self.assertIn('event: error', failed.text)
            self.assertNotIn('event: done', failed.text)
            self.assertEqual(len(client.get(f'/conversations/{chat_id}', headers=auth('alice')).json()['messages']), before_failure)
            self.assertEqual(client.get(f"/conversations/{response['conversation_id']}", headers=auth('bob')).status_code, 404)
            empty = client.post('/questions', json={'question':'火星宇宙飞船引擎设计'}, headers=auth('alice')).json()
            self.assertEqual(empty['citations'], [])
            self.assertIn('未找到', empty['answer'])
            self.assertEqual(client.post('/documents/1/retire', headers=auth('admin')).status_code, 200)
            self.assertEqual(client.post('/questions', json={'question':'冷链试剂验收温度记录'}, headers=auth('alice')).json()['citations'], [])
            with patch.dict(os.environ, {'PILOT_JWT_SECRET':'x'*40}):
                self.assertEqual(client.post('/auth/login', json={'username':'admin','password':'wrong'}).status_code, 401)
                login = client.post('/auth/login', json={'username':'admin','password':'test-password-123'})
                self.assertEqual(login.status_code, 200, login.text)
                admin_auth = {'Authorization':'Bearer ' + login.json()['access_token']}
                self.assertEqual(client.get('/me', headers=admin_auth).json()['role'], 'admin')
                self.assertEqual(client.post('/admin/prompts', json={'content':'请引用制度内容。'}, headers=auth('alice')).status_code, 403)
                self.assertEqual(client.post('/admin/prompts', json={'content':'请引用制度内容。'}, headers=admin_auth).status_code, 201)
                self.assertEqual(client.get('/admin/prompts', headers=admin_auth).json()[0]['content'], '请引用制度内容。')
                upload = client.post('/admin/documents', data={'title':'上传制度','version':'v1'}, files={'file':('policy.md','采购试剂需要核对浓度和包装。'.encode('utf-8'),'text/markdown')}, headers=admin_auth)
                self.assertEqual(upload.status_code, 201, upload.text)
                self.assertEqual(client.post('/admin/documents', data={'title':'错误','version':'v1'}, files={'file':('bad.txt',b'text','text/plain')}, headers=admin_auth).status_code, 422)
                self.assertEqual(client.get('/admin/audit/conversations', headers=auth('alice')).status_code, 403)
                self.assertGreater(len(client.get('/admin/audit/conversations', headers=admin_auth).json()), 0)
                self.assertEqual(client.get('/admin-ui').status_code, 200)
                from io import BytesIO
                from pypdf import PdfWriter
                from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
                writer=PdfWriter(); page=writer.add_blank_page(width=200,height=200)
                font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
                page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
                pdfstream=DecodedStreamObject(); pdfstream.set_data(b'BT /F1 12 Tf 20 100 Td (Cold chain inspection) Tj ET'); page[NameObject('/Contents')]=pdfstream
                pdf=BytesIO(); writer.write(pdf)
                pdf_response=client.post('/admin/documents',data={'title':'PDF制度','version':'v1'},files={'file':('policy.pdf',pdf.getvalue(),'application/pdf')},headers=admin_auth)
                self.assertEqual(pdf_response.status_code,201,pdf_response.text)
                message_id=client.get('/admin/audit/conversations',headers=admin_auth).json()[0]['message_id']
                self.assertEqual(client.post(f'/admin/audit/messages/{message_id}/flags',json={'reason':'人工复核'},headers=admin_auth).status_code,201)
                captured_template=[]
                async def check_template(question, citations, history, template=None):
                    captured_template.append(template)
                    yield '示例'
                with patch('my_tool.api.chat.generate_answer',check_template):
                    client.post('/chat',json={'question':'采购试剂浓度和包装'},headers=auth('alice'))
                self.assertEqual(captured_template[-1],'请引用制度内容。')
                for _ in range(5):
                    self.assertEqual(client.post('/auth/login', json={'username':'no-such-account','password':'invalid'}).status_code, 401)
                self.assertEqual(client.post('/auth/login', json={'username':'no-such-account','password':'invalid'}).status_code, 429)
                self.assertEqual(client.post('/auth/logout',headers=admin_auth).status_code,200)
                self.assertEqual(client.get('/me',headers=admin_auth).status_code,401)
            os.environ.pop('AGENT_MODEL', None)
            policy_run = client.post('/agent/run', json={'question':'冷链试剂验收温度记录'}, headers=auth('alice'))
            self.assertIn('search_policy', policy_run.text)
            self.assertIn('event: done', policy_run.text)
            request2 = client.post('/requests', json={**payload,'business_id':'DEMO-AGENT'}, headers=auth('alice')).json()
            from datetime import date as current_date
            with patch('my_tool.api.agent.date') as mocked_date:
                mocked_date.today.return_value = current_date(2026,10,23)
                result = client.post('/agent/run', json={'question':'核查并交接', 'version_id':request2['version_id'],'receiver_id':users['reviewer']}, headers=auth('alice'))
            self.assertIn('event: confirmation_required', result.text, result.text)
            events = [(line[7:],json.loads(nxt[6:])) for line,nxt in zip(result.text.splitlines(),result.text.splitlines()[1:]) if line.startswith('event: ') and nxt.startswith('data: ')]
            draft = next(v for k,v in events if k == 'confirmation_required')
            self.assertEqual(client.post(f"/agent/drafts/{draft['draft_id']}/confirm", json={'confirm':True}, headers=auth('bob')).status_code, 404)
            confirmed = client.post(f"/agent/drafts/{draft['draft_id']}/confirm", json={'confirm':True}, headers=auth('alice'))
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            self.assertFalse(confirmed.json()['approved'])
            self.assertEqual(client.post(f"/agent/drafts/{draft['draft_id']}/confirm", json={'confirm':True}, headers=auth('alice')).status_code, 409)
            self.assertEqual(client.get(f"/handoffs/{confirmed.json()['handoff_id']}",headers=auth('reviewer')).json()['status'],'pending')
            async def bad_planner(question, completed, mode, observations): return 'prepare_handoff'
            with patch('my_tool.api.agent.choose_tool',bad_planner):
                rejected = client.post('/agent/run', json={'question':'跳过检查','version_id':request2['version_id'],'receiver_id':users['reviewer']}, headers=auth('alice'))
                self.assertIn('event: error', rejected.text)
            evidence = client.post('/agent/run', json={'question':'核对凭证','version_id':request2['version_id']}, headers=auth('alice'))
            self.assertIn('check_evidence', evidence.text)

from my_tool.api.agent import choose_tool
from unittest.mock import patch
import json
import httpx

class AgentPlannerTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_adapter_sends_previous_tool_results(self):
        received = []
        def handler(request):
            received.append(json.loads(request.content))
            return httpx.Response(200, json={'choices':[{'message':{'tool_calls':[{'function':{'name':'finish','arguments':'{}'}}]}}]})
        real_client = httpx.AsyncClient
        def client(**kwargs): return real_client(transport=httpx.MockTransport(handler), **kwargs)
        env = {'AGENT_MODEL':'mock','MODEL_API_BASE':'https://example.test/v1','MODEL_API_KEY':'fake'}
        with patch.dict(os.environ,env), patch('my_tool.api.agent.httpx.AsyncClient',side_effect=client):
            result = await choose_tool('查看制度',['search_policy'],'policy',[{'tool':'search_policy','result':{'message':'未找到'}}])
        self.assertEqual(result,'finish')
        self.assertIn('未找到', received[0]['messages'][1]['content'])
        self.assertTrue(received[0]['tools'])


if __name__ == '__main__':
    unittest.main()
