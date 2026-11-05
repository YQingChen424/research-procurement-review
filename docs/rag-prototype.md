# 科研采购制度问答：命令行原型

该原型是单独的 [Python 脚本](../scripts/procurement_rag.py)，读取 [模拟制度](../data/sample_procurement_policy.md)，按每 500 个字符切片，建立 FAISS 向量索引和基于 jieba 中文分词的 BM25 索引；两路结果使用倒数排名融合，最多取 3 个片段，回答后显示文件名及行号。索引保存在 `.rag_index/`，已加入 `.gitignore`。

它与现有 CLI、FastAPI 和数据库服务互不替代。该制度完全虚构；回答不是采购、安全或预算审批。

## 本地离线演示

在项目根目录，使用 Python 3.11+ 安装依赖：

```powershell
python -m pip install -r requirements.txt
```

首次运行、制度更新或向量模型变更后重建索引：

```powershell
python scripts/procurement_rag.py --demo --rebuild
```

随后输入问题，例如“冷链试剂验收需要检查什么？”，输入 `exit` 或 `quit` 退出。也可以一次性提问：

```powershell
python scripts/procurement_rag.py --demo --question '冷链试剂验收需要检查什么？'
python scripts/procurement_rag.py --demo --question '火星宇宙飞船引擎设计原理是什么？'
```

演示模式使用本地字符哈希向量和制度摘录，**不会调用大模型，也不能代表真实语义检索质量**。默认的相关性阈值只是演示启发式；在正式使用前应使用真实问题和人工标注评估召回、误召回与拒答效果。

## 配置真实供应商

将以下环境变量设为支持 OpenAI 兼容 `/embeddings` 和 `/chat/completions` 接口的服务配置：

- `MODEL_API_BASE`：API 基础地址，包含供应商要求的版本路径。
- `MODEL_API_KEY`：API 密钥，通过环境变量提供，不写入代码或索引。
- `EMBEDDING_MODEL`：供应商的向量模型名称。
- `CHAT_MODEL`：供应商的对话模型名称。

配置后，在项目根目录运行：

```powershell
python scripts/procurement_rag.py --rebuild
```

未配置模型时，程序会列出缺失的变量。脚本将制度文本和用户问题发送到配置的供应商；当前只应使用虚构数据。模型适配器目前仅覆盖上述兼容接口，不保证支持每家供应商的差异化参数。切片大小是 500 个字符，不保证等同于模型的 500 个 token。

修改制度、切换向量模型、切换 API 基础地址、或从演示模式切换至真实模式时，须使用 `--rebuild` 重建。脚本会校验文档内容、模型标识和索引文件是否与元数据一致，但文件哈希不能防止恶意篡改；只加载自己创建、位于可信目录中的 FAISS 索引。

可用 `--document path/to/policy.md` 指定另一个 UTF-8 Markdown 文件，使用 `--index-dir path/to/index` 为不同制度指定独立目录。文档与分块内容会保存在索引元数据中，不要将敏感材料或索引提交到仓库。

## 验证

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -v
```

自动化测试覆盖分段和行号、FAISS 检索、无依据拒答、文档变更后的索引失效，以及模型适配函数的模拟请求。真实供应商凭据尚未配置，真实模型调用尚未验证；模型回答和来源是否匹配也必须人工检查。
