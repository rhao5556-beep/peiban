"""
冲突检测服务 - 识别和处理矛盾记忆
"""
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class ConflictDetector:
    """
    冲突检测器
    
    功能：
    1. 检测矛盾的记忆（喜欢 vs 讨厌）
    2. 基于时间戳判断哪个更新
    3. 生成澄清问题
    """
    
    # 对立关系词
    OPPOSITE_PAIRS = [
        ("喜欢", "讨厌"),
        ("喜欢", "不喜欢"),
        ("爱", "恨"),
        ("想要", "不想要"),
        ("需要", "不需要"),
        ("是", "不是"),
        ("有", "没有"),
    ]

    _TOPIC_TRIGGER_WORDS = [
        "喜欢", "不喜欢", "讨厌", "爱", "恨", "想要", "不想要", "需要", "不需要",
        "来自", "住在", "生活在", "工作在", "工作于", "在",
    ]

    _CH_STOPWORDS = {
        "这个", "那个", "这些", "那些", "真的", "其实", "感觉", "可能", "应该",
        "今天", "昨天", "明天", "最近", "一直", "有点", "非常", "特别",
        "因为", "所以", "但是", "而且", "并且", "同时", "如果", "的话",
        "我们", "你们", "他们", "她们", "它们", "自己", "以及",
        "我", "你", "他", "她", "它", "人", "东西",
    }
    
    def detect_conflicts(
        self,
        memories: List[Dict],
        threshold: float = 0.8
    ) -> List[Dict]:
        """
        检测记忆中的冲突
        
        Args:
            memories: 记忆列表，每个记忆包含 content, created_at, id
            threshold: 冲突判定阈值（语义相似度）
            
        Returns:
            冲突列表，每个冲突包含：
            - memory_1: 第一条记忆
            - memory_2: 第二条记忆
            - conflict_type: 冲突类型（opposite, contradiction）
            - confidence: 置信度
            - newer_memory: 更新的记忆
        """
        conflicts = []
        
        for i, mem1 in enumerate(memories):
            for mem2 in memories[i+1:]:
                conflict = self._check_conflict(mem1, mem2)
                if conflict and conflict["confidence"] >= threshold:
                    conflicts.append(conflict)
        
        return conflicts
    
    def _check_conflict(
        self,
        mem1: Dict,
        mem2: Dict
    ) -> Optional[Dict]:
        """
        检查两条记忆是否冲突
        
        检测规则：
        1. 包含对立词（喜欢 vs 讨厌）
        2. 主题相同（都是关于"茶"）
        3. 时间不同（不是同一次表述）
        """
        # 支持字典和 dataclass 对象
        content1 = (mem1.get("content", "") if isinstance(mem1, dict) else mem1.content).lower()
        content2 = (mem2.get("content", "") if isinstance(mem2, dict) else mem2.content).lower()
        
        # 检查是否包含对立词
        has_opposite = False
        opposite_pair = None
        
        for word1, word2 in self.OPPOSITE_PAIRS:
            if (word1 in content1 and word2 in content2) or \
               (word2 in content1 and word1 in content2):
                has_opposite = True
                opposite_pair = (word1, word2)
                break
        
        if not has_opposite:
            return None
        
        topics1 = self._extract_topics(content1)
        topics2 = self._extract_topics(content2)
        common_topics = topics1 & topics2

        if not common_topics:
            return None
        
        # 判断哪个更新
        time1 = mem1.get("created_at", datetime.min) if isinstance(mem1, dict) else mem1.created_at
        time2 = mem2.get("created_at", datetime.min) if isinstance(mem2, dict) else mem2.created_at
        
        newer_memory = mem1 if time1 > time2 else mem2
        older_memory = mem2 if time1 > time2 else mem1
        
        return {
            "memory_1": mem1,
            "memory_2": mem2,
            "conflict_type": "opposite",
            "opposite_pair": opposite_pair,
            "common_topic": sorted(common_topics),
            "confidence": self._estimate_confidence(opposite_pair, topics1, topics2),
            "newer_memory": newer_memory,
            "older_memory": older_memory,
            "time_diff_days": abs((time1 - time2).days) if time1 and time2 else 0
        }
    
    def _extract_topics(self, text: str) -> set[str]:
        if not text:
            return set()

        topics: set[str] = set()

        for m in re.finditer(
            r"(喜欢|不喜欢|讨厌|爱|恨|想要|不想要|需要|不需要|来自|住在|生活在|工作在|工作于|在)\s*(?P<obj>[^\n，。！？!?;；,]{1,24})",
            text,
        ):
            obj = (m.group("obj") or "").strip()
            obj = re.sub(r"^(吃|喝|玩|看|听|做|去|学|练|跑|打|写)\s*", "", obj)
            obj = re.sub(r"\s+", "", obj)
            obj = re.sub(r"[\"'“”‘’]+", "", obj)
            if obj and obj not in self._CH_STOPWORDS and len(obj) <= 24:
                topics.add(obj)

        for token in re.findall(r"[\u4e00-\u9fff]{2,8}", text):
            if token not in self._CH_STOPWORDS:
                topics.add(token)

        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,24}", text):
            token_l = token.lower()
            if token_l not in {"like", "dislike"}:
                topics.add(token_l)

        return topics

    def _estimate_confidence(self, opposite_pair: Tuple[str, str], topics1: set[str], topics2: set[str]) -> float:
        if not topics1 or not topics2:
            return 0.6
        common = topics1 & topics2
        overlap = len(common) / max(len(topics1), len(topics2), 1)
        base = 0.75 if opposite_pair else 0.6
        return max(0.5, min(0.95, base + overlap * 0.25))
    
    def generate_clarification_prompt(
        self,
        conflict: Dict
    ) -> str:
        """
        生成澄清问题
        
        Args:
            conflict: 冲突信息
            
        Returns:
            澄清问题文本
        """
        mem1 = conflict["memory_1"]
        mem2 = conflict["memory_2"]
        newer = conflict["newer_memory"]
        topic = conflict["common_topic"][0] if conflict["common_topic"] else "这个"
        
        # 支持字典和 dataclass 对象
        mem1_id = mem1.get("id") if isinstance(mem1, dict) else mem1.id
        mem1_content = mem1.get("content") if isinstance(mem1, dict) else mem1.content
        mem2_content = mem2.get("content") if isinstance(mem2, dict) else mem2.content
        newer_id = newer.get("id") if isinstance(newer, dict) else newer.id
        
        # 判断哪个是新的
        is_mem1_newer = (mem1_id == newer_id)
        
        clarification = f"""
【检测到矛盾信息】

我记得你之前说过：
1. {mem1_content}
2. {mem2_content}

这两个说法有点矛盾。能帮我确认一下吗？

选项：
A. 第一个是对的（{mem1_content[:20]}...）
B. 第二个是对的（{mem2_content[:20]}...）
C. 都不对，实际情况是...
"""
        
        return clarification.strip()
    
    def resolve_conflict_with_time(
        self,
        conflict: Dict
    ) -> Dict:
        """
        基于时间戳解决冲突（最新优先）
        
        Args:
            conflict: 冲突信息
            
        Returns:
            解决方案：
            - preferred_memory: 优先使用的记忆
            - reason: 原因
        """
        newer = conflict["newer_memory"]
        time_diff = conflict["time_diff_days"]
        
        # 如果时间差很小（< 1天），可能是同一次对话的不同表述
        if time_diff < 1:
            reason = "时间太近，可能是同一次对话，建议澄清"
            return {
                "preferred_memory": None,
                "reason": reason,
                "action": "clarify"
            }
        
        # 如果时间差较大，优先使用最新的
        reason = f"最新的记忆（{time_diff}天前）更可能反映当前偏好"
        return {
            "preferred_memory": newer,
            "reason": reason,
            "action": "use_newer"
        }


# 使用示例
if __name__ == "__main__":
    detector = ConflictDetector()
    
    # 测试数据
    memories = [
        {
            "id": "1",
            "content": "我喜欢茶",
            "created_at": datetime(2026, 1, 10)
        },
        {
            "id": "2",
            "content": "我讨厌茶",
            "created_at": datetime(2026, 1, 15)
        },
        {
            "id": "3",
            "content": "我喜欢淡淡的茶",
            "created_at": datetime(2026, 1, 18)
        }
    ]
    
    # 检测冲突
    conflicts = detector.detect_conflicts(memories)
    
    print(f"检测到 {len(conflicts)} 个冲突：")
    for conflict in conflicts:
        print(f"\n冲突：")
        print(f"  记忆1: {conflict['memory_1']['content']}")
        print(f"  记忆2: {conflict['memory_2']['content']}")
        print(f"  主题: {conflict['common_topic']}")
        print(f"  时间差: {conflict['time_diff_days']} 天")
        
        # 生成澄清问题
        clarification = detector.generate_clarification_prompt(conflict)
        print(f"\n澄清问题：")
        print(clarification)
        
        # 基于时间解决
        resolution = detector.resolve_conflict_with_time(conflict)
        print(f"\n解决方案：")
        print(f"  行动: {resolution['action']}")
        print(f"  原因: {resolution['reason']}")
