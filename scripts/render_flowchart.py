"""Render the editable procurement pilot flowchart as PNG and SVG."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Ellipse, FancyArrowPatch, Polygon, Rectangle
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
)
FONT_PATH = next((path for path in FONT_CANDIDATES if path.exists()), None)
FONT = font_manager.FontProperties(fname=str(FONT_PATH)) if FONT_PATH else font_manager.FontProperties(family="sans-serif")

COLORS = {
    "start": ("#EBF7EA", "#339447"),
    "process": ("#EAF2FC", "#6C9BCE"),
    "decision": ("#FFF3D6", "#D8A746"),
    "exception": ("#FDECEF", "#DB7882"),
    "output": ("#F1E9FC", "#A584D0"),
}

fig, ax = plt.subplots(figsize=(13, 20), dpi=180)
plt.rcParams["svg.fonttype"] = "none"
fig.patch.set_facecolor("#FFFFFF")
ax.set_facecolor("#FFFFFF")
ax.set_xlim(0, 14)
ax.set_ylim(0, 22.35)
ax.axis("off")

nodes: dict[str, tuple[float, float, float, float]] = {}


def node(name: str, label: str, kind: str, x: float, y: float, w: float = 4.10, h: float = 0.77) -> None:
    fill, stroke = COLORS[kind]
    if kind == "decision":
        h = 0.98
        shape = Polygon([(x, y + h / 2), (x + w / 2, y), (x, y - h / 2), (x - w / 2, y)], closed=True)
    elif kind == "start":
        h = 0.70
        shape = Ellipse((x, y), w, h)
    else:
        shape = Rectangle((x - w / 2, y - h / 2), w, h)
    shape.set(facecolor=fill, edgecolor=stroke, linewidth=1.35, zorder=3)
    ax.add_patch(shape)
    nodes[name] = (x, y, w, h)
    size = 10.7 if kind == "start" else 10.1
    ax.text(x, y, label, ha="center", va="center", fontsize=size, color="#243442", fontproperties=FONT, linespacing=1.25, zorder=4)


def side(name: str, where: str) -> tuple[float, float]:
    x, y, w, h = nodes[name]
    return {
        "top": (x, y + h / 2),
        "bottom": (x, y - h / 2),
        "left": (x - w / 2, y),
        "right": (x + w / 2, y),
    }[where]


def arrow(points: list[tuple[float, float]], label: str | None = None, label_at: tuple[float, float] | None = None) -> None:
    if len(points) > 2:
        xs, ys = zip(*points[:-1])
        ax.plot(xs, ys, color="#95A1A8", linewidth=1.25, zorder=1)
    ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle="-|>", mutation_scale=11, color="#849199", linewidth=1.25, zorder=2))
    if label and label_at:
        ax.text(*label_at, label, ha="center", va="center", fontsize=9, color="#3D4C57", fontproperties=FONT, bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.3}, zorder=5)


ax.text(7, 21.89, "澄岳研究院——科研采购规格核对与交接辅助流程图", ha="center", va="center", fontsize=17.5, fontproperties=FONT, color="#1C3342", weight="bold")
ax.text(7, 21.47, "只读辅助 · 人工审批 · 证据留痕 · 异常可回退", ha="center", va="center", fontsize=10, fontproperties=FONT, color="#687985")

node("start", "开始：课题组提交试剂采购申请", "start", 7, 20.62)
node("intake", "建立业务编号、资料版本\n记录规格、包装、货期和用途", "process", 7, 19.42)
node("complete", "申请信息完整且\n试剂标识唯一？", "decision", 7, 18.22)
node("complete_fix", "保留待办：补齐规格 / CAS / SKU\n歧义记录进人工修复队列", "exception", 2.2, 18.22, 3.45)
node("read", "只读查询采购平台、ERP、库存表\n记录来源与最后同步时间", "process", 7, 17.02)
node("fresh", "数据版本有效且\n来源可用？", "decision", 7, 15.82)
node("fresh_fix", "停止提示：人工查询原系统\n修复字段映射或过期记录", "exception", 2.2, 15.82, 3.45)
node("compare", "辅助核对浓度、包装、货期\n生成差异提示；不选择供应商", "process", 7, 14.62)
node("conflict", "有规格冲突或\n标识歧义？", "decision", 7, 13.42)
node("conflict_fix", "标注差异与证据\n交采购专员人工确认", "exception", 2.2, 13.42, 3.45)
node("review", "采购专员复核提示\n记录采纳 / 驳回理由与版本", "process", 7, 12.22)
node("approval", "对应岗位完成人工审批\n核验危化资质、冷链与预算", "process", 7, 11.02)
node("approved", "资质、验收材料及\n审批链均通过？", "decision", 7, 9.82)
node("approval_fix", "暂停采购：记录缺项、责任人\n补证后由原审批岗位复核", "exception", 11.8, 9.82, 3.45)
node("handoff", "发起交接：编号、版本、状态\n未决事项与接手人一并发送", "process", 7, 8.62)
node("received", "接手人已确认？", "decision", 7, 7.42)
node("received_fix", "保留原岗位待办\n超时提醒并升级负责人", "exception", 2.2, 7.42, 3.45)
node("arrival", "到货前提示验收人\n记录到货时间、温控与交接时间", "process", 7, 6.22)
node("evidence", "到货验收证据完整？", "decision", 7, 5.02)
node("evidence_fix", "安全异常暂停验收\n人工复核温控与责任归属", "exception", 2.2, 5.02, 3.45)
node("output", "输出只读辅助建议和复核记录\n按业务编号统计轮次、等待与异常", "output", 7, 3.82)
node("end", "结束：本次交接闭环，进入试点评估", "start", 7, 2.62)

for first, second in (
    ("start", "intake"), ("intake", "complete"), ("complete", "read"),
    ("read", "fresh"), ("fresh", "compare"), ("compare", "conflict"),
    ("conflict", "review"), ("review", "approval"), ("approval", "approved"),
    ("approved", "handoff"), ("handoff", "received"), ("received", "arrival"),
    ("arrival", "evidence"), ("evidence", "output"), ("output", "end"),
):
    label = None
    if first in {"complete", "fresh", "approved", "received", "evidence"}:
        label = "是"
    if first == "conflict":
        label = "否"
    p1, p2 = side(first, "bottom"), side(second, "top")
    arrow([p1, p2], label, (p1[0] + 0.25, (p1[1] + p2[1]) / 2) if label else None)

for decision, exception, answer in (
    ("complete", "complete_fix", "否"), ("fresh", "fresh_fix", "否"),
    ("conflict", "conflict_fix", "是"), ("received", "received_fix", "否"),
    ("evidence", "evidence_fix", "否"),
):
    p1, p2 = side(decision, "left"), side(exception, "right")
    arrow([p1, p2], answer, ((p1[0] + p2[0]) / 2, p1[1] + 0.17))

arrow([side("approved", "right"), side("approval_fix", "left")], "否", (9.4, 9.99))

for exception, back_to in (
    ("complete_fix", "intake"), ("fresh_fix", "read"),
    ("received_fix", "handoff"), ("evidence_fix", "arrival"),
):
    x, y = side(exception, "top")
    target = side(back_to, "left")
    arrow([(x, y), (0.52, y), (0.52, target[1]), target])

arrow([side("conflict_fix", "bottom"), (2.2, 12.22), side("review", "left")])
x, y = side("approval_fix", "top")
target = side("approval", "right")
arrow([(x, y), (13.5, y), (13.5, target[1]), target])

ax.text(7, 1.52, "颜色说明：", ha="right", va="center", fontsize=9, fontproperties=FONT, color="#54636C")
legend = [("起止", "start"), ("处理", "process"), ("判断", "decision"), ("异常 / 人工", "exception"), ("输出", "output")]
for idx, (label, kind) in enumerate(legend):
    x = 7.12 + idx * 1.31
    fill, stroke = COLORS[kind]
    ax.add_patch(Rectangle((x, 1.39), 0.20, 0.20, facecolor=fill, edgecolor=stroke, linewidth=1))
    ax.text(x + 0.26, 1.49, label, ha="left", va="center", fontsize=8.1, fontproperties=FONT, color="#54636C")

ax.text(7, 0.70, "基于合成场景 24/36 条访谈事实；审批与安全口径仍待岗位确认。图示为待验证的试点流程。", ha="center", va="center", fontsize=8.5, fontproperties=FONT, color="#71808A")
ax.text(7, 0.37, "证据：research-procurement-f10 / f11 / f23 / f31 / f32 / f33 / f40 / f41 / f42", ha="center", va="center", fontsize=8.1, fontproperties=FONT, color="#71808A")

OUT.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT / "flowchart.svg", bbox_inches="tight", pad_inches=0.18)
fig.savefig(OUT / "flowchart.png", bbox_inches="tight", pad_inches=0.18, dpi=180)
plt.close(fig)
with Image.open(OUT / "flowchart.png") as png:
    png.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(
        OUT / "flowchart.png", optimize=True
    )
