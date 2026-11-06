"""Generate traceable course documents; requires python-docx and Pillow."""
from pathlib import Path
from datetime import date
import csv,json,shutil
from PIL import Image,ImageDraw,ImageFont
from docx import Document
from docx.shared import Cm,Pt
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'docs'; T=ROOT/'tests'; S=ROOT/'src'
for p in (D,T,S,D/'访谈资料',D/'流程图',T/'figures'):p.mkdir(parents=True,exist_ok=True)
def write(path,text):path.write_text(text.strip()+'\n',encoding='utf-8')
def draw(path,title,items):
 img=Image.new('RGB',(1400,200+len(items)*170),'#f4f8f6'); d=ImageDraw.Draw(img); f=lambda n:ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',n)
 d.text((55,35),title,font=f(38),fill='#153f39');y=125
 for i,(a,b,kind) in enumerate(items):
  d.rounded_rectangle((70,y,1330,y+120),radius=18,fill={'h':'#fff1ce','e':'#fbe4dd'}.get(kind,'#dff0ea'),outline='#94b9ad',width=2)
  d.text((100,y+15),str(i+1)+'  '+a,font=f(28),fill='#153f39');d.text((100,y+66),b,font=f(22),fill='#405f58')
  if i<len(items)-1:d.line((700,y+120,700,y+155),fill='#49786d',width=4);d.polygon([(690,y+148),(710,y+148),(700,y+161)],fill='#49786d')
  y+=170
 img.save(path)

def make_doc(mdpath,docpath,figures=()):
 doc=Document();style=doc.styles['Normal'];style.font.name='Microsoft YaHei';style._element.rPr.rFonts.set(qn('w:eastAsia'),'Microsoft YaHei');style.font.size=Pt(10)
 sec=doc.sections[0];sec.top_margin=sec.bottom_margin=Cm(2);sec.left_margin=sec.right_margin=Cm(2)
 if 'ROI' in docpath.name:
  sec.orientation=WD_ORIENT.LANDSCAPE;sec.page_width,sec.page_height=sec.page_height,sec.page_width
 make_doc.in_table=False
 for line in mdpath.read_text(encoding='utf-8').splitlines():
  if line.startswith('# '):doc.add_heading(line[2:],0)
  elif line.startswith('## '):doc.add_heading(line[3:],1)
  elif line.startswith('### '):doc.add_heading(line[4:],2)
  elif line.startswith('|'):
   vals=[x.strip() for x in line.strip().strip('|').split('|')]
   if all(set(x)<=set(':- ') for x in vals):continue
   table=doc.tables[-1] if doc.tables and getattr(make_doc,'in_table',False) and len(doc.tables[-1].columns)==len(vals) else doc.add_table(rows=0,cols=len(vals))
   table.style='Table Grid';cells=table.add_row().cells
   for cell,val in zip(cells,vals):cell.text=val
   make_doc.in_table=True
  elif line.strip():
   make_doc.in_table=False;doc.add_paragraph(line[2:] if line.startswith('- ') else line,style='List Bullet' if line.startswith('- ') else None)
  else:make_doc.in_table=False
 for fig in figures:
  doc.add_paragraph('图示：依据当前文档或测试记录绘制，非业务现场截图。');doc.add_picture(str(fig),width=Cm(15))
 doc.core_properties.title=mdpath.stem;doc.save(docpath);make_doc.in_table=False

facts=[('顾明岚','f00','管理目标：18天降至10天；紧急采购占比27%降至低于12%。'),('顾明岚','f01','申请、库存核查、比价、审批、验收；节点耗时未测量。'),('顾明岚','f02','试点设想20种常用试剂、6周、规格审核准确率目标至少98%。'),('顾明岚','f03','初始预算12万元含集成、培训、验证，维护与人工复核成本需计入。'),('顾明岚','f04','安全负责人对上线有否决权。'),('林亦舟','f10','规格相近、货期不同，反复确认浓度和包装。'),('林亦舟','f11','冷藏试剂周五到货无人验收，次日发现温控记录缺失。'),('林亦舟','f12','访谈转述160申请/月、平均4轮核对、每轮20分钟，需核实口径。'),('林亦舟','f13','高峰期使用既有终端，需草稿保存和同步时间。'),('唐映秋','f20','节点需输入、输出、负责人和退回原因。'),('唐映秋','f21','材料包括规格、三份报价、危险品清单、温度日志。'),('唐映秋','f22','采购不得代替安全签署或自主选择供应商。'),('唐映秋','f23','交接应包含编号、版本、状态、未决事项并经接收人确认。'),('秦芮','f30','采购平台、ERP和库存表权限分离。'),('秦芮','f31','CAS、品名与供应商SKU存在标识映射问题。'),('秦芮','f32','系统数据可读；不得自动付款或危险品审批。'),('秦芮','f33','歧义记录进入人工修复队列。'),('傅景','f40','危险品资质、冷链验收和预算审批不可绕过。'),('傅景','f41','仅授权角色可查看原始记录。'),('傅景','f42','发生安全条件时应暂停试点。'),('傅景','f43','模拟记录暂定保留90天，实际期限待确认。'),('角色待核','f51','按业务单测量交接等待与重复联系，固定统计口径。'),('角色待核','f53','投诉关联业务编号与版本。'),('角色待核','f54','不承诺未经确认的赔偿或结果。')]
records=[{'角色':r,'证据编号':'research-procurement-'+i,'事实摘录':v,'状态':'历史合成事实摘要；非逐字对话，当前练习待复核'} for r,i,v in facts]
write(D/'访谈资料'/'六角色证据摘录.json',json.dumps({'说明':'基于docs/design.md中24条模拟事实摘要，不是六人完整逐字访谈。叶书原话和角色待核记录待补。','facts':records},ensure_ascii=False,indent=2))
with (D/'访谈资料'/'六角色证据摘录.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['角色','证据编号','事实摘录','状态']);w.writeheader();w.writerows(records)
lines=['# 六角色访谈事实摘录（非逐字稿）','来源：仓库 docs/design.md 历史模拟案例24/36条事实。当前练习林亦舟有3轮原文；其他角色完整原始对话尚未取得。']
for role in ['顾明岚','林亦舟','唐映秋','秦芮','傅景','叶书','角色待核']:
 lines+=['','## '+role]; group=[x for x in records if x['角色']==role]; lines += [f"- {x['证据编号']}：{x['事实摘录']}" for x in group] or ['- 无可核对的该角色逐字访谈；待从训练平台导出。']
write(D/'访谈资料'/'六角色证据摘录.md','\n'.join(lines))
src=ROOT/'docs'/'interviews'/'林亦舟_冷链异常访谈.txt'
if src.exists():shutil.copy2(src,D/'访谈资料'/'典型事件访谈.txt')
write(D/'访谈资料'/'原始材料缺口.md','''# 原始材料缺口
- 已有：仓库24条历史模拟事实摘要、本次林亦舟三轮对话文本；不是六人完整逐字记录。
- 缺少：六人原始访谈导出；平台四份原始材料：客户简报、现状信息请求表、业务发现访谈问题库、利益相关者资料与分工。本目录没有用摘要冒充原文件。
- 未取得真实采购单、温度日志、审批凭证和企业授权；案例为合成训练。''')
draw(D/'流程图'/'01_改造前.png','改造前：试剂采购与交接',[('提交采购申请','实验人员填写需求及试剂规格','n'),('库存核查与比价','人工查库存、询价和确认货期','n'),('浓度包装反复确认','跨岗位确认；每单轮数须样本核实','h'),('预算与安全审批','由相应授权人员执行','h'),('冷链交接异常','案例：周五到货无人验收，次日发现温控记录缺失','e'),('人工追查和处置','发现人、损失、处置及耗时待核实','h')])
draw(D/'流程图'/'02_改造后.png','改造后：只读核查与人工确认',[('申请人确认字段','确认业务编号、CAS、浓度和包装','h'),('只读检索与规则检查','核对来源、版本、规格和证据缺口','n'),('采购人员审核','处理歧义、退回或补充资料','h'),('安全与预算审核','授权人员核验；系统不得代签','h'),('发起人确认草稿','展示接收人、版本及未决事项','h'),('接收人确认交接','记录确认时间；未确认保持待接收','h')])
industry='''# 行业分析：科研试剂采购与交付
## 范围与结论
本项目属于模拟科研试剂采购。规格、货期、供应商标识和冷链资料跨岗位流转，优先处理信息质量、可追溯交接和人工复核；资料并不能证明现有企业已取得改造收益。
## 公开资料及适用边界
- WHO温度敏感药品储运指南可借鉴温控记录与交接方法；其对象是药品，不能直接视作本科研试剂案例的法定义务。https://www.who.int/publications/m/item/trs961-annex9-modelguidanceforstoragetransport/
- GS1 Verified by GS1介绍GTIN等标识的商品和组织信息检索；不能假定全部试剂都有GTIN，或与CAS一一对应。https://www2.gs1.org/services/verified-by-gs1
- NIST AI风险管理框架强调设计、使用、评估中的风险治理，其生成式AI附录可作为人工监督和测试参考，并非案例审批制度。https://www.nist.gov/itl/ai-risk-management-framework
## 建议
P0：确定性核对、缺证转人工与交接确认；P1：带来源的制度问答、标识映射、节点计时；P2：趋势分析和模型迭代。样本、成本、制度版本、权限及适用规则须先经业务方确认。'''
write(D/'行业分析.md',industry)
req='''# 科研采购需求定义、规格追溯与验收
## 目标和范围
基于f10-f12、f23、f40：优先解决浓度包装反复确认、冷链证据缺口和交接责任不清。拟选20种试剂试点6周，准确率目标98%，清单和分母待确认。系统只读核查外部系统，可保存本地草稿；不得自动选择供应商、采购、危险品审批或付款。
## AI改造和优先级
| 优先级 | 痛点及改造 | 人工与系统边界 |
| --- | --- | --- |
| P0 | CAS、浓度和包装由确定性规则核对，AI解释差异 | 申请人确认字段、采购复核；歧义不自动推荐 |
| P0 | 冷链、预算和安全证据缺失标记 | 授权人员核验证据并审批；申请声明不等于真实凭证 |
| P0 | 整理交接草稿并跟踪接收 | 发起人确认、接收人独立确认；未确认不算完成 |
| P1 | 制度问答引用、CAS/名称/SKU映射 | 无依据拒答；标识歧义进入人工队列 |
| P2 | 质量统计、模型迭代 | 数据授权及真实标注后评估 |
## 需求规格与追溯矩阵
| 编号 | 证据与痛点 | 需求边界 | 验收标准 | 当前状态 |
| --- | --- | --- | --- | --- |
| R01 | f10/f31 | CAS浓度包装精确比对，不自行换算 | 标注集正确审核比例目标≥98%；分母先约定 | 规则原型，真实标注待测 |
| R02 | f33 | 缺失、过期、多候选转人工 | 多候选不输出唯一SKU，三类异常均触发 | 模拟测试部分覆盖 |
| R03 | f11/f40 | 缺温控、安全、预算分别标记 | 各缺失样例均提示；绝不自动批准 | 原型；真实证据未接入 |
| R04 | f20/f22 | 记录采购审核人、结论和原因 | 抽样全部可关联业务ID与版本 | 模拟API |
| R05 | f23 | 发起人确认草稿，接收人独立确认 | 未确认时待接收；重复确认拒绝 | 模拟测试已覆盖 |
| R06 | f21/f41 | 制度问答引用有效来源，无依据拒答 | 制度外至少3题拒答且不编造，引用可定位 | 演示；文档级权限未完成 |
| R07 | f30/f32 | 外部系统只读和角色认证 | 测试矩阵零越权、无自动付款或采购 | 模拟权限，正式SSO待接 |
| R08 | f15/f23 | 业务ID、版本、规则、交接可追溯 | 各测试记录可定位，历史不静默覆盖 | 部分实现，防篡改待补 |
| R09 | f02/f12 | 固定样本窗口测准确率及确认轮次 | 事前确定双人标注、分母、排除项 | 待试点 |
| R10 | f40/f42 | 安全异常暂停并移交 | 缺证、越权、冲突均转人工；停用机制人工核准 | 原型部分支持 |
## 验收清单
- 标注样本须覆盖匹配、不匹配、歧义、缺失及过期；准确率=正确审核单数/有效标注单数，样本和争议仲裁先确定。
- 至少三个人工检查点：申请人确认字段、采购人工复核、发起人确认交接草稿、接收人确认；危险品/预算/冷链另由授权人员核验。现有系统不等于完成正式审批。
- 验证正常、边界、对抗、权限、故障五类；安全角色、真实源数据、授权矩阵和真实客户验收均待确认。
- 记录问答引用、无答案拒答、基线、采用率和人工复核结果；未经实测不能认定已节省时间。'''
write(D/'需求定义与追溯矩阵.md',req)
design='''# 详细项目设计方案
## 总体架构
入口：FastAPI、制度问答、采购核查、管理后台；服务：申请版本、规则审核、交接、文档、会话和审计；编排：最多五轮工具决策、BM25+FAISS与可替换模型适配；数据：SQLite试点或PostgreSQL+pgvector。详细表结构见仓库 docs/architecture.md。
## 业务流程
申请人确认规格→只读获取目录与制度→规则核对差异和证据→采购人员复核→授权人员另行核验安全与预算→发起人确认交接草稿→接收人确认→审计留痕。至少三处人工确认贯穿输入、审核、交接；模型不决定安全结论。
## 输入输出与异常
输入包含业务编号、版本、CAS、浓度、包装、来源时间和证据状态；输出状态、原因、来源、规则版本与审核记录。目录歧义、缺证、权限不足、来源过期或模型失败时停止自动建议并转人工；已保存的声明不证明凭证真实。
## 角色及权限
申请人可管理自己的申请并确认本人发起的交接草稿；采购审核人查看申请并记录人工意见；被指定接收人单独确认交接；管理员维护制度。安全负责人独立负责安全判断。正式环境须建立岗位授权矩阵，实施最小权限和定期复核；管理员不自动获得所有业务记录。申请字段的独立人工确认是目标流程，当前没有专门的签字确认状态。
## 模块和数据流
入口对请求认证和输入校验；申请服务写入业务编号和版本快照；目录和制度检索返回来源及时间；规则引擎计算原因并保留规则版本；人员决定后保存审核意见。交接工具展示待确认草稿，经发起人确认才创建待接收记录，接收人再次确认；日志关联操作人、对象和时间。不得以模型输出覆盖原始申请或替代授权人的决定。
数据包括用户、申请、版本、审核结果、交接、制度和切片、会话消息、审计及智能体步骤。当前证据只是声明和目录快照，真实文件存储、验签与证据授权需设计后接入。外部系统只读接口需明确字段映射、有效期、故障超时及退回机制。
## 智能体控制
政策咨询只需检索；处理交接时，服务端强制先取申请、查目录、核规格及检查证据，再允许准备草稿，最多五轮；缺证、异常或超限停止并转人工。模型提示词只作辅助约束，强制条件由服务端校验；草稿确认和接收确认分开。当前本地演示使用模拟规划器，真实模型可配置但尚未做现场联调。
## 非功能与部署设计
试点默认本机SQLite，生产环境应按并发、备份和恢复验证确定数据库；服务与密钥分离，传输加密、留存期、审计权限和备份加密由客户批准。记录请求耗时、错误数与人工移交数，约定告警阈值和负责人。提供版本化部署与数据库备份，回滚前确认迁移可逆及数据恢复演练；上述均为上线前目标，不宣称已实现。
## 实施与验收
第1周确认试点清单、角色、基线和字段；第2–3周完成只读对接与规则映射；第4–5周小范围试运行、记录异常与人工耗时；第6周根据标注集、权限矩阵和恢复演练组织验收。排期为规划而非已完成事实，需按数据和接口可用性调整。验收依据见需求追溯矩阵和量化测试方案。
## 当前缺口
企业SSO、文档级授权、正式接口和证据核验、扫描PDF识别、真实模型联调、故障恢复及真实验收尚未完成。模型接口使用本地模拟规划器，不能宣称已上线生产。'''
write(D/'详细项目设计方案.md',design)
scenarios=[('低',60000,1000,.3,10,.5),('中',100000,2200,.6,20,.7),('高',150000,4000,.85,30,.85)]
roi=['# 报价与ROI测算（全部为假设）','报价为课程模拟，非供应商承诺。160申请/月来自访谈转述，业务量、采用率、节省时间和兑现率均未实测。人工成本假设80元/小时，全年12个月不变；节省是可释放工作能力，不自动等于现金收益。','## 报价与范围','| 档位 | 一次性投入 | 每月运行成本 | 假设范围 |','| --- | --- | --- | --- |','| 低 | 60,000元 | 1,000元 | 本地规则、制度问答、基础培训，不含正式接口 |','| 中 | 100,000元 | 2,200元 | 增加一个获授权只读接口、审计及试点支持 |','| 高 | 150,000元 | 4,000元 | 多系统适配、模型治理和扩展支持，不含自动审批付款 |','## 测算结果','| 档位 | 采用率 | 节省/单 | 兑现率 | 月收益 | 首年收益 | 首年总成本 | 首年净收益 | ROI | 回本期 |','| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
for name,upfront,monthly,adoption,minutes,realize in scenarios:
 benefit=160*adoption*minutes/60*realize*80; annual=benefit*12; cost=upfront+monthly*12; net=annual-cost; rate=net/cost*100; pay=upfront/(benefit-monthly) if benefit>monthly else None
 roi.append(f'| {name} | {adoption:.0%} | {minutes}分钟 | {realize:.0%} | {benefit:,.0f}元 | {annual:,.0f}元 | {cost:,.0f}元 | {net:,.0f}元 | {rate:.1f}% | '+(f'{pay:.1f}个月' if pay else '月净贡献≤0，无法回本')+' |')
roi+=['## 月运行成本构成（估算，元/月）','| 档位 | 云资源及存储 | 模型与检索 | 运维支持 | 合计 |','| --- | --- | --- | --- | --- |','| 低 | 400 | 300 | 300 | 1,000 |','| 中 | 700 | 600 | 900 | 2,200 |','| 高 | 1,200 | 1,000 | 1,800 | 4,000 |','费用为假设预算，不是供应商实时报价。实施费用包含范围内开发、测试和交付；采购设备、正式安全测评及第三方系统改造须另议。','## 公式与待验证','月收益=160×采用率×节省分钟÷60×兑现率×80；首年总成本=一次性投入+12×月运行成本；首年净收益=12×月收益-首年总成本；ROI=首年净收益÷首年总成本；回本期=一次性投入÷(月收益-月运行成本)，仅月净贡献为正时计算。未计折现税费，不计未经证实的损失避免。','中档首年成本126,400元，高于案例12万元初始预算；预算边界和费用分项需确认。高档回本期约240.4个月；低、中档月净贡献非正。','待验证：业务量与测量窗口、每单净节省与复核新增时间、采用率、兑现率、人工成本、报价和月成本分项、试点周期以及安全审批。']
write(D/'报价与ROI测算.md','\n'.join(roi))
runbook='''# 上线交付运行手册（本地试点）
## 当前状态
本地模拟，不是生产上线或客户验收。代码：https://github.com/YQingChen424/research-procurement-review 。仅用虚构数据，禁止自动采购、付款或安全审批。
## 启动和访问
在项目根目录执行 python -m pip install -r requirements.txt，再运行 python scripts/start_demo.py。访问 http://127.0.0.1:8876/chat-ui、/agent-ui、/admin-ui。管理员账号demo-admin，演示令牌和密码在 .local_demo 目录，不能提交到Git或公开。localhost仅当前电脑可访问，不是公网部署地址。
## 操作与人工确认
申请人填写并确认规格；采购人员审核；发起人确认交接草稿；接收人使用独立账号确认。安全、预算、冷链证据由授权人员核验，现有声明不代表完成审批。出现缺证、冲突、过期、无权或模型错误时停止并转人工。
## 交付前待完成
确认系统接口和只读权限、角色矩阵、数据保留与备份、密钥、真实模型、告警、成本、恢复与回滚负责人；业务、安全和系统负责人确认验收。正式SSO、OCR、真实采购数据和模型联调尚未完成。'''
write(D/'上线交付运行手册.md',runbook)
write(S/'源码与部署地址.md','''# 源码与部署状态
- 项目源码位于仓库 src/my_tool；问答原型 scripts/procurement_rag.py；演示 scripts/start_demo.py。
- GitHub：https://github.com/YQingChen424/research-procurement-review
- 本机演示：http://127.0.0.1:8876/chat-ui ，核查 /agent-ui，管理 /admin-ui，仅本机。
- 公网部署地址：未提供。不得把 localhost 写成可供他人访问的线上地址；待部署环境、安全控制和验收后补充。''')

incident='''# 冷链异常典型事件访谈整理
## 来源和真实性
2026-11-06与训练平台合成角色林亦舟进行三轮问答，逐字内容见同目录《典型事件访谈.txt》。这是模拟角色陈述，不能当成真实企业采访。
## 事件时间线
- 周五：冷藏试剂到货时实验室无人验收。
- 次日：发现温控记录缺失；不知道具体时间、发现人、供应商和试剂名称，也没有证据证明处理时长、是否重购、实验损失或本次事件的最终结果。
- 一般处理习惯：暂停相关建议，由采购专员核对原记录，不覆盖错误结果；不能据此认定这一次的实际处置。
## 其他痛点及量化线索
规格相近、货期不同，浓度和包装需反复确认。受访者转述采购侧约160申请/月、平均每单核对4轮、每轮约20分钟；其没有逐单计时，上述数据不是本次冷链事件的数据，也不能直接当作可节省工时。
## 追问和需求
需要调查具体发现时间、负责人、原始温度记录、使用和实验影响；核实160、4、20的样本和统计口径。需求候选是到货前提示责任人、缺证转人工、保留原记录、记录发起人与接收人确认。'''
write(D/'访谈资料'/'典型事件访谈整理.md',incident)
plan='''# MVP量化测试方案
## 范围与环境
基于本仓库模拟数据、FastAPI测试客户端及独立数据库。证据为 evidence.json，结果来自运行 scripts/run_course_tests.py；所有案例均为受控模拟，并非生产、安全渗透或客户验收。可重跑命令：python scripts/run_course_tests.py；单元测试：python -m unittest discover -s tests -v。
## 五类案例与通过标准
| 编号 | 类别 | 输入或操作 | 可量化通过标准 | 追溯 |
| --- | --- | --- | --- | --- |
| T01 | 正常 | 匹配目录与完整声明 | 1/1进入人工复核且approved=false | R01 R03 |
| T02 | 边界 | 两条同规格候选 | 1/1返回歧义且匹配SKU为0 | R02 |
| T03 | 权限 | 其他申请人读取申请 | 1/1返回404且不暴露内容 | R07 |
| T04 | 对抗 | 模型跳过校验直接准备交接 | 1/1产生错误且草稿事件为0 | R05 R10 |
| T05 | 故障 | 模型生成中途抛错 | 1/1错误事件、完成事件0、消息保存0 | R06 R10 |
## 实际执行与上线验收区别
本次五类各1项，5/5通过；仓库单元测试14项通过。通过只说明对应输入和受控模拟下表现符合断言，不代表全部安全场景或真实审批通过。进一步按真实标注集覆盖不匹配、缺失、过期、重复、不同角色和故障恢复；审核准确率≥98%为试点目标，应先约定样本数、分母、抽样方式和仲裁流程，再由业务方签字。'''
write(T/'量化测试方案.md',plan)
results=json.loads((T/'evidence.json').read_text(encoding='utf-8'))
for case in results['cases']:
 name=case['name']; fig=T/'figures'/(name+'.png')
 draw(fig,name+'：自动测试过程',[('输入',case['input'],'n'),('操作',' → '.join(case['steps']),'n'),('预期',case['expected'],'h'),('实际结果',case['observed'],'n' if case['passed'] else 'e')])
 content=['# '+name+'测试过程','## 执行依据','受控模拟自动测试；流程图根据实测记录绘制，不是现场截图。','证据文件：tests/evidence.json；UTC时间：'+results['timestamp_utc'],'## 输入',case['input'],'## 执行步骤']
 content.extend([f'{i}. {v}' for i,v in enumerate(case['steps'],1)])
 content+=['## 预期与实际','预期：'+case['expected'],'实际：'+case['observed'],'结论：'+('通过' if case['passed'] else '失败'),'## 限制','仅覆盖当前一条模拟输入；不构成正式上线验收。']
 md=T/(name+'测试过程.md');write(md,'\n'.join(content));make_doc(md,T/(name+'测试.docx'),[fig])
for title in ['行业分析','需求定义与追溯矩阵','详细项目设计方案','报价与ROI测算','上线交付运行手册']:
 figs=[D/'流程图'/'01_改造前.png',D/'流程图'/'02_改造后.png'] if title=='详细项目设计方案' else []
 make_doc(D/(title+'.md'),D/(title+'.docx'),figs)
make_doc(D/'访谈资料'/'典型事件访谈整理.md',D/'访谈资料'/'典型事件访谈整理.docx')
make_doc(T/'量化测试方案.md',T/'量化测试方案.docx')
make_doc(S/'源码与部署地址.md',S/'源码与部署地址.docx')
write(D/'课程交付说明.md','''# 科研采购课程交付包
## 已整理
- docs/访谈资料：三轮训练角色事件访谈原文与整理、六角色历史事实摘录（Markdown、JSON、CSV）。摘录不是六人逐字稿。
- docs/流程图：改造前后两张PNG；行业分析、需求与追溯、设计、报价ROI和运行手册均提供Word及Markdown。
- tests：五类受控模拟自动测试数据、量化方案、每类过程图和Word；执行方法见量化方案。
- src：源码入口、演示地址与公网部署状态；实际代码位于仓库 src/my_tool。
## 仍缺材料及验收
六人完整原始访谈、四份平台原始简报、可公网访问的正式部署地址、企业真实数据和真实验收都未取得；不能以模拟事实、localhost或模拟测试结果替代。请在可访问平台和服务器后补齐，且勿将令牌、密码或真实敏感数据提交仓库。
## 生成与复测
python scripts/run_course_tests.py
安装python-docx与Pillow后，运行 python scripts/build_course_delivery.py。运行环境需要Windows中文字体。''')
print(f'已生成交付文档至 docs、src、tests；五类模拟测试 {results["passed"]}/{results["total"]}。')
