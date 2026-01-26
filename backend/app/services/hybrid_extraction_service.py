"""
混合实体抽取服务 - 规则引擎 + LLM 回退

优化策略：
1. 简单实体（人名、地名）用规则引擎快速提取（< 10ms）
2. 复杂关系或歧义情况才调用 LLM（~1-2s）
3. 缓存常见实体模式

性能目标：
- 简单消息（如"昊哥住在大连"）：< 50ms
- 复杂消息（如"我认识的人谁住在海边"）：< 2s
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from app.services.llm_extraction_service import extract_ir, ExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class RuleMatch:
    """规则匹配结果"""
    entity_name: str
    entity_type: str  # Person, Location, Preference
    relation_type: Optional[str] = None  # LIVES_IN, FROM, LIKES, etc.
    target_name: Optional[str] = None
    confidence: float = 0.9


class HybridExtractionService:
    """
    混合实体抽取服务
    
    规则引擎处理：
    - 简单陈述句（主语 + 动词 + 宾语）
    - 常见关系模式（住在、来自、喜欢）
    - 明确的人名、地名
    
    LLM 处理：
    - 复杂句式（多个子句、嵌套）
    - 歧义消解
    - 新颖表达
    """
    
    # 常见中文人名模式
    PERSON_PATTERNS = [
        r'([\u4e00-\u9fa5]{2,4})(哥|姐|妹|弟|sir|老师|同学|朋友)',  # 昊哥、张sir
        r'(小[\u4e00-\u9fa5]{1,2})',  # 小明、小红
        r'(老[\u4e00-\u9fa5]{1,2})',  # 老王、老李
        r'([\u4e00-\u9fa5]{2,3})',  # 二丫、张伟
    ]
    
    # 常见地名（可扩展）
    KNOWN_LOCATIONS = {
        '北京', '上海', '广州', '深圳', '杭州', '成都', '重庆', '武汉',
        '西安', '南京', '天津', '苏州', '大连', '青岛', '厦门', '哈尔滨',
        '长春', '沈阳', '济南', '郑州', '长沙', '南昌', '合肥', '福州',
        '海南', '三亚', '昆明', '贵阳', '兰州', '银川', '乌鲁木齐', '拉萨',
        '中国', '美国', '日本', '韩国', '英国', '法国', '德国', '澳大利亚',
    }
    
    # 关系模式（简单句式）
    RELATION_PATTERNS = [
        # 地理关系
        (r'(.+?)(住在|住|在)(.+)', 'LIVES_IN', 'Location'),
        (r'(.+?)(来自|来源于|是)(.+?)(人|的)', 'FROM', 'Location'),
        (r'(.+?)(工作在|上班在)(.+)', 'WORKS_AT', 'Location'),
        
        # 偏好关系
        (r'(.+?)(喜欢|爱|热爱|喜爱)(.+)', 'LIKES', 'Preference'),
        (r'(.+?)(不喜欢|讨厌|不爱|厌恶)(.+)', 'DISLIKES', 'Preference'),
        
        # 家庭关系
        (r'(.+?)(是|叫)(.+?)(的)?(妈妈|母亲|爸爸|父亲)', 'PARENT_OF', 'Person'),
        (r'(.+?)(的)?(妈妈|母亲|爸爸|父亲)(是|叫)(.+)', 'CHILD_OF', 'Person'),
        (r'(.+?)(是|叫)(.+?)(的)?(哥哥|弟弟|姐姐|妹妹)', 'SIBLING_OF', 'Person'),
        (r'(.+?)(的)?(哥哥|弟弟|姐姐|妹妹)(是|叫)(.+)', 'SIBLING_OF', 'Person'),
        
        # 社交关系
        (r'(.+?)(是|叫)(.+?)(的)?(朋友|好友)', 'FRIEND_OF', 'Person'),
        (r'(.+?)(的)?(朋友|好友)(是|叫)(.+)', 'FRIEND_OF', 'Person'),
        (r'(.+?)(是|叫)(.+?)(的)?(同事)', 'COLLEAGUE_OF', 'Person'),
    ]
    
    # 提问句特征（不应提取关系）
    QUESTION_MARKERS = [
        '？', '吗', '呢', '是否', '是不是',
        '谁', '什么', '哪里', '怎么', '为什么', '多少',
        '认识', '知道', '记得'
    ]
    
    def __init__(self):
        self._compiled_person_patterns = [re.compile(p) for p in self.PERSON_PATTERNS]
        self._compiled_relation_patterns = [
            (re.compile(pattern), rel_type, target_type)
            for pattern, rel_type, target_type in self.RELATION_PATTERNS
        ]
    
    async def extract(
        self,
        text: str,
        user_id: str,
        context_entities: List[Dict[str, Any]],
        force_llm: bool = False
    ) -> ExtractionResult:
        """
        混合提取实体和关系
        
        Args:
            text: 用户消息
            user_id: 用户 ID
            context_entities: 已存在的实体列表
            force_llm: 强制使用 LLM（用于测试）
        
        Returns:
            ExtractionResult
        """
        # 1. 快速判断：是否为提问句
        if self._is_question(text):
            logger.info(f"Detected question, skipping extraction: {text[:50]}")
            return self._empty_result()
        
        # 2. 尝试规则引擎
        if not force_llm:
            rule_result = self._try_rule_extraction(text, user_id, context_entities)
            
            if rule_result and rule_result.success:
                logger.info(f"Rule engine success: {len(rule_result.entities)} entities, {len(rule_result.relations)} relations")
                return rule_result
        
        # 3. 回退到 LLM
        logger.info(f"Falling back to LLM extraction for: {text[:50]}")
        return extract_ir(text, user_id, context_entities)
    
    def _is_question(self, text: str) -> bool:
        """判断是否为提问句"""
        # 检查提问标记
        for marker in self.QUESTION_MARKERS:
            if marker in text:
                return True
        
        # 检查是否以问号结尾
        if text.strip().endswith('？') or text.strip().endswith('?'):
            return True
        
        return False
    
    def _try_rule_extraction(
        self,
        text: str,
        user_id: str,
        context_entities: List[Dict[str, Any]]
    ) -> Optional[ExtractionResult]:
        """
        尝试使用规则引擎提取
        
        Returns:
            ExtractionResult if successful, None if should fallback to LLM
        """
        # 检查复杂度
        if self._is_complex(text):
            logger.debug(f"Text too complex for rules: {text[:50]}")
            return None
        
        # 提取实体和关系
        matches = self._extract_with_rules(text, context_entities)
        
        if not matches:
            logger.debug(f"No rule matches found: {text[:50]}")
            return None
        
        # 转换为标准格式
        entities = []
        relations = []
        
        # 添加 user 实体
        entities.append({
            "id": "user",
            "name": "我",
            "type": "Person",
            "is_user": True,
            "confidence": 1.0
        })
        
        # 处理匹配结果
        for match in matches:
            # 添加实体
            entity_id = self._normalize_entity_id(match.entity_name, context_entities)
            
            entity = {
                "id": entity_id,
                "name": match.entity_name,
                "type": match.entity_type,
                "is_user": False,
                "confidence": match.confidence
            }
            
            if entity not in entities:
                entities.append(entity)
            
            # 添加关系
            if match.relation_type and match.target_name:
                target_id = self._normalize_entity_id(match.target_name, context_entities)
                
                # 添加目标实体
                target_entity = {
                    "id": target_id,
                    "name": match.target_name,
                    "type": self._infer_type(match.target_name),
                    "is_user": False,
                    "confidence": match.confidence
                }
                
                if target_entity not in entities:
                    entities.append(target_entity)
                
                # 创建关系
                relation = {
                    "source": entity_id,
                    "target": target_id,
                    "type": match.relation_type,
                    "desc": f"{match.entity_name} {match.relation_type} {match.target_name}",
                    "weight": 0.8,
                    "confidence": match.confidence
                }
                
                relations.append(relation)
        
        # 构建结果
        metadata = {
            "source": "rule_engine",
            "model_version": "v1.0",
            "timestamp": datetime.utcnow().isoformat(),
            "overall_confidence": 0.85
        }
        
        return ExtractionResult(
            success=True,
            entities=entities,
            relations=relations,
            metadata=metadata,
            raw_response=f"Rule engine extracted from: {text}"
        )
    
    def _is_complex(self, text: str) -> bool:
        """
        判断文本是否过于复杂，需要 LLM 处理
        
        复杂特征：
        - 多个子句（超过 2 个逗号/句号）
        - 包含"而且"、"但是"、"不过"等连接词
        - 包含否定 + 肯定（"不是X，是Y"）
        - 超过 50 字
        """
        # 长度检查
        if len(text) > 50:
            return True
        
        # 子句数量
        clause_count = text.count('，') + text.count('。') + text.count(',') + text.count('.')
        if clause_count > 2:
            return True
        
        # 复杂连接词
        complex_markers = ['而且', '但是', '不过', '然而', '虽然', '尽管', '不是', '并且']
        for marker in complex_markers:
            if marker in text:
                return True
        
        return False
    
    def _extract_with_rules(
        self,
        text: str,
        context_entities: List[Dict[str, Any]]
    ) -> List[RuleMatch]:
        """使用规则提取实体和关系"""
        matches = []
        
        # 尝试匹配关系模式
        for pattern, rel_type, target_type in self._compiled_relation_patterns:
            match = pattern.search(text)
            if match:
                groups = match.groups()
                
                # 提取主语和宾语
                subject = groups[0].strip() if len(groups) > 0 else None
                obj = groups[-1].strip() if len(groups) > 2 else None
                
                if subject and obj:
                    # 识别主语类型
                    subject_type = self._infer_type(subject)
                    
                    matches.append(RuleMatch(
                        entity_name=subject,
                        entity_type=subject_type,
                        relation_type=rel_type,
                        target_name=obj,
                        confidence=0.85
                    ))
                    
                    logger.debug(f"Rule match: {subject} -{rel_type}-> {obj}")
        
        # 如果没有关系匹配，尝试提取独立实体
        if not matches:
            # 提取人名
            for pattern in self._compiled_person_patterns:
                for match in pattern.finditer(text):
                    name = match.group(0)
                    matches.append(RuleMatch(
                        entity_name=name,
                        entity_type='Person',
                        confidence=0.8
                    ))
            
            # 提取地名
            for location in self.KNOWN_LOCATIONS:
                if location in text:
                    matches.append(RuleMatch(
                        entity_name=location,
                        entity_type='Location',
                        confidence=0.9
                    ))
        
        return matches
    
    def _normalize_entity_id(
        self,
        name: str,
        context_entities: List[Dict[str, Any]]
    ) -> str:
        """
        归一化实体 ID
        
        如果 context_entities 中有相同名称的实体，复用其 ID
        """
        for entity in context_entities:
            if entity.get('name') == name:
                return entity.get('id')
        
        # 生成新 ID
        return self._slugify(name)
    
    def _infer_type(self, name: str) -> str:
        """推断实体类型"""
        # 地名
        if name in self.KNOWN_LOCATIONS:
            return 'Location'
        
        # 人名模式
        for pattern in self._compiled_person_patterns:
            if pattern.match(name):
                return 'Person'
        
        # 默认为偏好/其他
        return 'Preference'
    
    def _slugify(self, name: str) -> str:
        """生成稳定的实体 ID"""
        import hashlib
        
        if not name:
            return "unknown"
        
        # 简单处理：使用 hash
        h = hashlib.md5(name.encode()).hexdigest()[:8]
        return f"{name}_{h}"
    
    def _empty_result(self) -> ExtractionResult:
        """返回空结果"""
        return ExtractionResult(
            success=True,
            entities=[{
                "id": "user",
                "name": "我",
                "type": "Person",
                "is_user": True,
                "confidence": 1.0
            }],
            relations=[],
            metadata={
                "source": "rule_engine",
                "model_version": "v1.0",
                "timestamp": datetime.utcnow().isoformat(),
                "overall_confidence": 1.0,
                "reason": "question_detected"
            }
        )
