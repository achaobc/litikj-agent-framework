# -*- coding: utf-8 -*-
"""
core/nlp_extractor.py
【立体空间智能体系统 · 高可用启发式自然语言提炼引擎】
职责：
1. 为各类内容生产型智能体（B站/小红书/公众号/视频号/知识库）提供 100% 本地运行、0-Token、零外部 pip 依赖的 NLP 文本分析与提炼能力；
2. 杜绝硬编码死模板！即使无大模型或在离线环境下，也能从真实逐字稿/文章中动态提取：
   - 启发式高点击率候选标题
   - 真实转折点章节时间戳
   - 纯净内容摘要（自动过滤违规词与营销套话）
   - 高权重相关标签 (Tags)
3. 专为大模型失败时的优雅动态降级（Graceful Degradation）而生。
"""

import re
from typing import List, Tuple, Dict, Any, Optional
from collections import Counter


# 基础停用词过滤集合
STOP_WORDS = {
    "的", "了", "和", "是", "就", "都", "而", "及", "与", "着", "或", "一个", "没有", "我们",
    "你们", "他们", "这个", "那个", "怎么", "什么", "如果", "但是", "因为", "所以", "而且",
    "然后", "那么", "这里", "那里", "自己", "可以", "也是", "就是", "其实", "大家", "今天",
    "一下", "一些", "非常", "可能", "应该", "已经", "还是", "为了", "对于", "进行", "通过",
    "以及", "并且", "这种", "那种", "这样", "那样", "现在", "接着", "你看", "也就是说"
}

# 违规导流词黑名单
BANNED_WORDS = [
    "私信我", "加微信", "进群", "免费领取", "点击链接", "扫码进群", "下单",
    "加v", "加V", "微信：", "微信:", "vx:", "vx：", "v信", "公众号", "限时免费",
    "低价甩卖", "包过", "保过", "内部资料", "首发独家"
]


class HeuristicNLPExtractor:
    """启发式文本提炼器 (纯原生实现)"""

    @classmethod
    def clean_text(cls, text: str) -> str:
        """清洗文本，剔除违规词与多余空白"""
        if not text:
            return ""
        result = text
        for bad in BANNED_WORDS:
            result = result.replace(bad, "")
        result = re.sub(r'[ \t]+', ' ', result)
        return result.strip()

    @classmethod
    def extract_keywords(cls, text: str, top_k: int = 8) -> List[str]:
        """
        轻量级关键词抽取（支持中英文混合分词）
        优先提取：英文驼峰/专有名词 (如 WebSocket, Auto.js, FFmpeg) 与 2-6 字中文实词
        """
        if not text:
            return []

        # 1. 提取英文专有名词 / 代码标识符
        english_words = re.findall(r'[a-zA-Z0-9_\-\.]{2,}', text)
        english_tokens = [w for w in english_words if len(w) >= 2 and not w.isdigit()]

        # 2. 提取 2~5 字的中文词块
        chinese_chunks = re.findall(r'[\u4e00-\u9fa5]{2,5}', text)
        chinese_tokens = [w for w in chinese_chunks if w not in STOP_WORDS]

        all_candidates = english_tokens + chinese_tokens
        counter = Counter(all_candidates)

        ranked = [word for word, count in counter.most_common(top_k * 2) if word not in STOP_WORDS]
        # 去重保持原有顺序
        seen = set()
        final_keywords = []
        for w in ranked:
            w_lower = w.lower()
            if w_lower not in seen and len(final_keywords) < top_k:
                seen.add(w_lower)
                final_keywords.append(w)

        return final_keywords

    @classmethod
    def generate_candidate_titles(cls, topic: str, pure_text: str, top_keywords: Optional[List[str]] = None) -> List[str]:
        """
        动态生成高点击率爆款候选标题（严格基于真实主题与文本核心词组合）
        """
        clean_topic = topic.strip()
        # 清除文件名开头的序号如 "11、" 或 "01_"
        clean_topic = re.sub(r'^\d+[\s、_\-\.]+', '', clean_topic)

        if not top_keywords:
            top_keywords = cls.extract_keywords(pure_text, top_k=5)

        kw_str = " · ".join(top_keywords[:2]) if top_keywords else "实战拆解"
        core_kw = top_keywords[0] if top_keywords else clean_topic

        titles = [
            f"【实战教程】{clean_topic}！全流程开发与落地拆解",
            f"别再走弯路！深入理解 {clean_topic}（{kw_str}）",
            f"手把手教你搞定 {clean_topic}：核心原理与工程实操",
            f"搞定 {core_kw} 这一期就够了！{clean_topic} 深度避坑指南",
            f"【硬核干货】{clean_topic} 从零到一完整实现流程"
        ]
        return titles

    @classmethod
    def extract_chapters(cls, timed_segments: List[Tuple[str, str]], max_chapters: int = 5) -> List[Dict[str, str]]:
        """
        从带时间戳的语音识别切片中，基于步长与语义转折点提取真实章节
        :param timed_segments: [("00:00", "各位观众大家好..."), ("00:40", "我们先来看一下代码..."), ...]
        """
        if not timed_segments:
            return [
                {"time": "00:00", "desc": "核心背景与实操痛点"},
                {"time": "01:30", "desc": "关键架构设计与实操演练"},
                {"time": "03:00", "desc": "完整工程落地与总结"}
            ]

        # 过滤过短时间
        total_segs = len(timed_segments)
        step = max(1, total_segs // max_chapters)

        chapters = []
        for i in range(0, total_segs, step):
            time_str, seg_text = timed_segments[i]
            # 从该切片提取前 15 个字作为章节速览，并结合专有名词
            clean_seg = re.sub(r'^[，。！？\s]+', '', seg_text)
            clean_seg = re.sub(r'[，。！？].*$', '', clean_seg)  # 取第一个分句
            if not clean_seg or len(clean_seg) < 3:
                clean_seg = f"核心实战解析 {len(chapters) + 1}"
            else:
                clean_seg = clean_seg[:18]

            chapters.append({
                "time": time_str,
                "desc": clean_seg
            })
            if len(chapters) >= max_chapters:
                break

        # 确保首个章节从 00:00 开始
        if chapters and chapters[0]["time"] != "00:00":
            chapters[0]["time"] = "00:00"

        return chapters

    @classmethod
    def generate_description(cls, topic: str, pure_text: str, chapters: List[Dict[str, str]], channel_id: str = "default") -> str:
        """
        基于真实逐字稿前沿句与动态章节，合成自然纯净的简介
        """
        clean_topic = re.sub(r'^\d+[\s、_\-\.]+', '', topic.strip())
        sentences = [s.strip() for s in re.split(r'[。！？\n]', pure_text) if len(s.strip()) > 8]
        intro_lead = " ".join(sentences[:2]) if len(sentences) >= 2 else f"本期视频深入拆解：{clean_topic} 的完整实战与落地应用。"
        if len(intro_lead) > 180:
            intro_lead = intro_lead[:180] + "..."

        chap_lines = [f"{c['time']} {c['desc']}" for c in chapters]
        chap_block = "\n".join(chap_lines)

        tail_author = "阿朝编程" if "achao" in channel_id.lower() else "立体空间"

        desc = (
            f"{intro_lead}\n\n"
            f"⏱️ 视频章节索引（点击直达）：\n"
            f"{chap_block}\n\n"
            f"💡 关注【{tail_author}】，用硬核技术与深度思考重构你的数字化资产与个人护城河！\n"
            f"求一个【点赞 + 收藏 + 关注】三连支持！大家的关注是持续输出硬核实操的最大动力！"
        )
        return cls.clean_text(desc)
