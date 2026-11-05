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
from my_tool.db.models import User
from my_tool.db.session import Session

TOKENS = {'alice': 'a'*40, 'bob': 'b'*40, 'reviewer': 'c'*40, 'admin': 'd'*40}
def auth(name):
    return {'Authorization': 'Bearer ' + TOKENS[name]}

async def seed():
    async with Session() as db:
        for name, role in [('alice','applicant'), ('bob','applicant'), ('reviewer','reviewer'), ('admin','admin')]:
            db.add(User(username=name, role=role, token_hash=hashlib.sha256(TOKENS[name].encode()).hexdigest()))
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
            self.assertEqual(client.get(f"/conversations/{response['conversation_id']}", headers=auth('bob')).status_code, 404)
            empty = client.post('/questions', json={'question':'火星宇宙飞船引擎设计'}, headers=auth('alice')).json()
            self.assertEqual(empty['citations'], [])
            self.assertIn('未找到', empty['answer'])
            self.assertEqual(client.post('/documents/1/retire', headers=auth('admin')).status_code, 200)
            self.assertEqual(client.post('/questions', json={'question':'冷链试剂验收温度记录'}, headers=auth('alice')).json()['citations'], [])

if __name__ == '__main__':
    unittest.main()
