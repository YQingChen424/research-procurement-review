"""Contract tests for the external model adapter; no network or credentials required."""
import json
import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from my_tool.services import knowledge

class ExternalModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_embedding_and_chat_requests(self):
        received = []
        def handler(request):
            payload = json.loads(request.content)
            received.append((request.url.path, request.headers.get('authorization'), payload))
            if request.url.path.endswith('/embeddings'):
                return httpx.Response(200, json={'data': [{'embedding': [0.1] * 384}]})
            return httpx.Response(200, json={'choices': [{'message': {'content': '请检查温度记录 [1]'}}]})
        real_client = httpx.AsyncClient
        def fake_client(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)
        config = {'MODEL_API_BASE':'https://example.test/v1', 'MODEL_API_KEY':'test-token', 'EMBEDDING_MODEL':'test-embedding', 'CHAT_MODEL':'test-chat'}
        with patch.dict(os.environ, config), patch.object(knowledge.httpx, 'AsyncClient', side_effect=fake_client):
            vector = await knowledge.embed('冷链验收')
            output = await knowledge.answer('怎么验收？', [{'content':'检查温度记录。'}])
        self.assertEqual(len(vector), 384)
        self.assertEqual(output, '请检查温度记录 [1]')
        self.assertEqual([item[0] for item in received], ['/v1/embeddings', '/v1/chat/completions'])
        self.assertTrue(all(item[1] == 'Bearer test-token' for item in received))
        self.assertEqual(received[0][2]['model'], 'test-embedding')
        self.assertEqual(received[1][2]['model'], 'test-chat')
        self.assertIn('检查温度记录', received[1][2]['messages'][-1]['content'])

    async def test_invalid_dimensions_are_rejected(self):
        real_client = httpx.AsyncClient
        def fake_client(**kwargs):
            return real_client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'data':[{'embedding':[0.1]}]})), **kwargs)
        with patch.dict(os.environ, {'MODEL_API_BASE':'https://example.test/v1','MODEL_API_KEY':'test-token','EMBEDDING_MODEL':'model'}), patch.object(knowledge.httpx, 'AsyncClient', side_effect=fake_client):
            with self.assertRaisesRegex(RuntimeError, '384 dimensions'):
                await knowledge.embed('test')

    async def test_no_evidence_never_calls_provider(self):
        with patch.dict(os.environ, {'CHAT_MODEL':'model'}), patch.object(knowledge.httpx, 'AsyncClient', side_effect=AssertionError('unexpected call')):
            output = await knowledge.answer('test', [])
        self.assertIn('未找到', output)

if __name__ == '__main__':
    unittest.main()
