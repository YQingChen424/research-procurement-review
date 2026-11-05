# 科研采购审核与交接助手：第一阶段 API

当前为**模拟数据试点**：FastAPI 异步 API、SQLite 本地存储（或 PostgreSQL/pgvector）、现有确定性审核规则、人工复核和交接、制度文档分段检索。外部采购、ERP、库存系统不会被修改；系统不选供应商、不审批采购或安全事项、不付款。`ready_for_human_review` 仅代表本地规则未发现问题，最终仍需人工复核。

这是教学/探索性原型，不是生产系统：用户 Bearer token 是本地演示凭证，制度目前对所有登录用户可检索；文档没有细粒度权限、有效期或文件上传；申请人的审批和温度证据布尔值只是声明，**不验证外部凭证的真实性**。未实现正式审批、采购系统对接、审计防篡改、数据保留策略、数据库迁移和生产身份认证，不应接入真实敏感数据。

## 环境与启动（Windows PowerShell）

在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PYTHONPATH = 'src'
```

每个角色分别设置一个至少 32 字符的随机令牌，然后执行一次账号创建命令。不要把令牌提交到仓库或发送给他人：

```powershell
$env:PILOT_USERNAME = 'demo-applicant'
$env:PILOT_ROLE = 'applicant'
$env:PILOT_TOKEN = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
# 在安全的位置临时保存此令牌，后面用于访问接口
python -m my_tool.bootstrap
```

重复操作创建 `reviewer`、`admin`，需要时创建 `safety`。对已有用户名再次执行会轮换其令牌和角色；只有持有服务器环境和数据库的人员才应执行。启动：

```powershell
python -m uvicorn my_tool.api.app:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/docs`，在每个接口的 Authorization 请求头中填写 `Bearer <令牌>`。按以下顺序体验：

1. 用申请人令牌调用 `POST /requests`，填入模拟试剂申请，记下 `version_id`。
2. 调用 `POST /versions/{version_id}/reviews`，输入模拟目录和检查日期；未交接时会提示 `handoff_unconfirmed`。目录和过期阈值来自请求，仅供试点验证，不是可信生产数据源。
3. 用 `GET /users` 查找采购审核人 ID；申请人调用 `POST /handoffs` 指定接收人，审核人调用 `POST /handoffs/{id}/confirm`。重新执行审核可得到新的审核快照。
4. 审核人调用 `POST /reviews/{id}/decision` 记录复核意见；即使选择 accepted，`approved` 仍为 false。
5. 管理员调用 `POST /documents` 录入模拟文本，每行作为一个段落。用户调用 `POST /questions` 查看摘录、文档版本及段落引用。管理员可用 `POST /documents/{id}/retire` 停用旧版本。
6. 使用 `GET /requests`、`GET /versions/{id}/reviews`、`GET /handoffs` 和 `GET /conversations/{id}` 查看有权访问的记录。

交接确认检查针对该申请版本的**最新交接**。提交新申请版本后须重新交接；审核结果是运行时快照，交接或数据变化后要重新审核。人工复核只针对对应审核快照。

## 模型与数据库配置

默认不请求外部服务：使用本地 384 维字符哈希向量做演示检索，回答为检索到的摘录，不能代表真正的语义检索质量。默认 SQLite 文件为 `pilot.db`，已加入 `.gitignore`。

要使用兼容 OpenAI 风格接口的供应商，可设置 `MODEL_API_BASE`（含 API 版本路径）、`MODEL_API_KEY` 和 `EMBEDDING_MODEL`；所选嵌入模型必须输出 384 维。可选设置 `CHAT_MODEL` 生成回答。发送的问题和检索文本会传给该服务；仅在获准后使用。更换嵌入模型后旧文档不会被该模型检索，需要重新导入并检查；现阶段没有自动重建索引。模型回答应由人核对原文。

可选 PostgreSQL：先设置 `POSTGRES_PASSWORD` 并运行 `docker compose up -d`，然后设置 `DATABASE_URL` 为 `postgresql+asyncpg://pilot:<密码>@127.0.0.1:5432/procurement_pilot`（特殊字符需 URL 编码），再创建账号和启动。服务首次启动创建表和 vector 扩展；数据库账号需要相应权限。向量保存在 pgvector 列中，目前在应用端精确计算相似度，适合小规模演示，不具备大规模检索性能。SQLite 与 PostgreSQL 是独立数据库，不自动迁移数据。

## 验证

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -s tests -v
python -m my_tool.main review --input data/sample_requests.json --as-of 2026-10-23
```

现有 CLI 的 JSON 格式见 [API 文档](api.md)，需求来源及未确认事项见 [项目设计](design.md)。

### 外部模型连通性验证

配置 `MODEL_API_BASE`、`MODEL_API_KEY`、`EMBEDDING_MODEL` 和 `CHAT_MODEL` 后，运行：

```powershell
python scripts/check_model_provider.py
```

脚本发送虚构的冷链文本，检查向量维度和非空回答，不打印密钥或模型回答；这只验证连通性，不代表回答质量已通过评估。向量模型必须返回 384 维。请勿向不具备授权的供应商发送真实采购数据。

PostgreSQL 集成测试可通过 `TEST_DATABASE_URL` 指向**专门的空测试数据库**后运行测试套件。测试会创建表并写入测试用户和记录，不能指向业务数据库。默认测试使用临时 SQLite 数据库。PostgreSQL 18 和 pgvector 的完整模拟业务流程已通过临时数据库验证；Docker Compose 部署仍需在本机 Docker 正常启动后验证。

## 制度聊天页面

完成本指南中的账号创建后，启动服务并打开 `http://127.0.0.1:8000/chat-ui`。管理员需先使用 `POST /documents` 添加模拟制度；然后在页面中输入申请人或审核人的演示令牌并提问。令牌仅保存在当前浏览器标签页，点击“新建会话”开始新的对话。

`POST /chat` 接收 `session_id`（首次为 null）和 `question`，返回 SSE `status`、`citations`、`delta`、`done` 或 `error`。成功后一次保存完整的问答和引用；连接中断或生成失败时不保存半轮。外部模型配置后会发送最近六轮完整问答与当前制度片段；未配置时显示本地摘录。目前页面对数据库中的有效制度段落建立临时 FAISS 索引，并进行 BM25 与向量融合检索；独立 CLI 使用的本地文件索引仍单独管理。SSE 会话并发锁仅适用于单进程演示，不适合多进程部署。

## 管理后台（试点）

启动服务前，在相同 PowerShell 会话中配置随机签名密钥并创建管理员账号（密码至少 12 位）：

```powershell
$env:PYTHONPATH = 'src'
$env:PILOT_JWT_SECRET = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$env:PILOT_USERNAME = 'pilot-admin'
$env:PILOT_ROLE = 'admin'
$env:PILOT_PASSWORD = Read-Host '输入试点管理员密码'
python -m my_tool.create_account
Remove-Item Env:PILOT_PASSWORD
python -m uvicorn my_tool.api.app:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/admin-ui` 登录。上传 UTF-8 Markdown 或可提取文本的 PDF（最多 2 MB、100 页），文档分片并索引；可发布问答模板、筛选审计消息及标记待复核。制度列表和停用使用已有接口 `GET /documents` 与 `POST /documents/{id}/retire`。模板追加在固定系统安全约束之后，不能替代权限校验。

JWT 默认有效 30 分钟；更改签名密钥将使旧 JWT 失效。此账号与旧演示令牌并存，登录密码使用 PBKDF2 哈希，尚未实现企业 SSO、令牌撤销、登录限流、文档级权限、审计员独立角色、PDF OCR 或生产级文件扫描。仅用于模拟试点，不可视为正式上线配置。
