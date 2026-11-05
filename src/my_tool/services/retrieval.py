"""数据库制度片段的中文 BM25 与向量排名融合。"""
import math
from collections import Counter
import jieba
import faiss
import numpy as np

jieba.setLogLevel(40)
STOP_WORDS = {'什么', '怎么', '怎么办', '如何', '需要', '可以', '是否', '应该', '请问', '有关', '规定', '要求', '制度', '进行', '以及', '相关', '一个', '这个', '的是', '哪些', '工作', '原理'}

def tokenize(text):
    return [term.lower() for term in jieba.lcut(text) if len(term.strip()) >= 2 and term not in STOP_WORDS and any(c.isalnum() for c in term)]

def rank_policy_chunks(question, vector, records):
    """按照中文分词和向量距离融合排序；门槛仅用于模拟演示。"""
    if not records:
        return []
    terms = set(tokenize(question))
    counts = [Counter(tokenize(chunk.content)) for chunk, _ in records]
    lengths = [sum(count.values()) for count in counts]
    avg = sum(lengths) / len(lengths) or 1
    lexical = []
    for count, length in zip(counts, lengths):
        matches = terms.intersection(count)
        score = 0.0
        # 至少两个有效词匹配，避免只凭“试剂”等通用词给出无关内容。
        if len(matches) >= 2:
            for term in matches:
                df = sum(term in item for item in counts)
                idf = math.log(1 + (len(counts) - df + 0.5) / (df + 0.5))
                tf = count[term]
                score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / avg))
        lexical.append(score)
    # 以当前有权限的有效数据库片段构建精确 FAISS 索引，避免引用已停用的本地文件索引。
    matrix = np.ascontiguousarray([list(chunk.embedding) for chunk, _ in records], dtype=np.float32)
    query_vector = np.ascontiguousarray(np.asarray(vector, dtype=np.float32).reshape(1, -1))
    if matrix.shape[1] != query_vector.shape[1]:
        raise ValueError('问题向量和制度向量维度不一致')
    faiss.normalize_L2(matrix)
    faiss.normalize_L2(query_vector)
    vector_index = faiss.IndexFlatIP(matrix.shape[1])
    vector_index.add(matrix)
    scores, positions = vector_index.search(query_vector, len(records))
    vector_scores = [0.0] * len(records)
    for i, score in zip(positions[0], scores[0]):
        if i >= 0: vector_scores[int(i)] = float(score)
    combined = {}
    for values, threshold in [(lexical, 0), (vector_scores, 0.25)]:
        order = sorted(range(len(records)), key=lambda i: values[i], reverse=True)
        for position, i in enumerate(order, 1):
            if values[i] > threshold:
                combined[i] = combined.get(i, 0) + 1 / (60 + position)
    return [records[i] for i in sorted(combined, key=lambda i: (-combined[i], i))[:3]]


def retrieval_question(question, history):
    """演示模式下为含指代的追问附上上一轮用户问题，供检索使用。"""
    cues = ('它', '这个', '那个', '这样', '这些', '他', '她', '那谁', '那这个', '那这个制度', '等价品')
    if any(cue in question for cue in cues):
        previous = next((item['content'] for item in reversed(history) if item['role'] == 'user'), '')
        if previous:
            return previous + ' ' + question
    return question
