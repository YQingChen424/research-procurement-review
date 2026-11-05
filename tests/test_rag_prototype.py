"""验证单文件 RAG 原型的索引、混合检索和无依据拒答。"""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'procurement_rag.py'
spec = importlib.util.spec_from_file_location('procurement_rag', SCRIPT)
rag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag)

class RagPrototypeTest(unittest.TestCase):
    def test_chunks_and_line_references(self):
        chunks = rag.split_document('甲乙\n丙丁\n戊己', 'policy.md', size=3)
        self.assertEqual([c['text'] for c in chunks], ['甲乙\n', '丙丁\n', '戊己'])
        self.assertEqual([(c['start_line'], c['end_line']) for c in chunks], [(1, 1), (2, 2), (3, 3)])

    def test_faiss_retrieval_refusal_and_stale_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            doc = root / 'test.md'
            doc.write_text('冷链试剂到货时应核对温度记录。', encoding='utf-8')
            config = rag.model_config(True)
            chunks, index, bm25 = rag.build_index(doc, root / 'index', config)
            chunks, index, bm25 = rag.load_index(doc, root / 'index', config)
            result = rag.retrieve('冷链试剂到货检查温度记录', chunks, index, bm25, config)
            self.assertTrue(result)
            self.assertEqual(result[0]['source'], 'test.md')
            no_sources = rag.retrieve('火星宇宙飞船引擎设计原理', chunks, index, bm25, config)
            self.assertEqual(no_sources, [])
            self.assertIn('无法确认', rag.call_llm('火星', no_sources, config))
            doc.write_text('修改后的其他制度。', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '重建'):
                rag.load_index(doc, root / 'index', config)

    def test_independent_model_functions_use_supplier_format(self):
        config = {'base':'https://example.test/v1', 'key':'placeholder', 'embedding_model':'embedding', 'chat_model':'chat'}
        with patch.object(rag, 'api_post', side_effect=[{'data':[{'embedding':[3.0,4.0]}]}, {'choices':[{'message':{'content':'检查温度记录 [1]'}}]}]) as api:
            vector = rag.embed_text('冷链', config)
            answer = rag.call_llm('冷链怎么验收', [{'text':'检查温度记录。'}], config)
        self.assertAlmostEqual(float(vector[0]), 0.6, places=5)
        self.assertEqual(answer, '检查温度记录 [1]')
        self.assertEqual(api.call_args_list[0].args[1], '/embeddings')
        self.assertEqual(api.call_args_list[1].args[1], '/chat/completions')
        self.assertIn('检查温度记录', api.call_args_list[1].args[2]['messages'][1]['content'])

    def test_no_evidence_does_not_contact_llm(self):
        with patch.object(rag, 'api_post', side_effect=AssertionError('unexpected call')):
            result = rag.call_llm('问题', [], {'chat_model':'external'})
        self.assertIn('无法确认', result)

if __name__ == '__main__':
    unittest.main()
