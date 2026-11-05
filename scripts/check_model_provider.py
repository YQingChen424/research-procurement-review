"""Optional real-provider smoke test. Sends only fabricated sample text."""
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from my_tool.services.knowledge import answer, embed

async def main():
    names = ['MODEL_API_BASE', 'MODEL_API_KEY', 'EMBEDDING_MODEL', 'CHAT_MODEL']
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        print('Missing environment variables: ' + ', '.join(missing), file=sys.stderr)
        return 2
    if os.environ['EMBEDDING_MODEL'] == 'local-hash-v1':
        print('Set EMBEDDING_MODEL to an external model for this test.', file=sys.stderr)
        return 2
    try:
        vector = await embed('模拟制度：冷链试剂验收需要检查温度记录。')
        response = await answer('冷链试剂验收需要检查什么？', [{'content': '模拟制度：冷链试剂验收需要检查温度记录。'}])
        if not isinstance(response, str) or not response.strip():
            raise ValueError('Empty model response')
    except Exception as exc:
        print('External provider test failed: ' + type(exc).__name__, file=sys.stderr)
        return 1
    print(f'External embedding and chat requests succeeded; vector dimensions: {len(vector)}.')
    print('Model response was nonempty; its factual accuracy was not automatically evaluated.')
    return 0

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
