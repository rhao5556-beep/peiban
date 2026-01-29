"""
LLM 实体抽取服务 - 图谱决策器

职责：
1. 组装 Prompt
2. 调用 OpenAI API
3. 校验并解析 IR JSON

架构决策：
- All-in LLM，不做正则降级
- 必须传入 recent_entities 作为实体消歧上下文
- IR 必须带 provenance（source, model_version, timestamp, confidence）
- 失败不写入，标记 pending_review
"""
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# OpenAI 兼容 API 配置（支持硅基流动等）
client = OpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.OPENAI_API_BASE
)
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3"
MODEL = settings.ENTITY_EXTRACTION_MODEL or settings.OPENAI_MODEL or DEFAULT_MODEL


SYSTEM_PROMPT = """你是 Affinity 系统的记忆架构师（Graph Decisioner）。你的任务是：

1) 从给定的中文消息中提取实体（Person, Location, Organization, Event, Preference, TimeExpression, Duration, Quantity, Other）
   和实体间的关系。

2) 执行实体归一化：
   - 如果识别到的实体与 context_entities 中名称相同或语义相近，必须复用其 id
   - 不得创建重复实体
   - 若无法归一化，基于中文名生成稳定 id（小写拼音/下划线）

3) 提取实体间关系（Entity→Entity），不仅仅是用户与实体的关系
   - 例如："二丫喜欢足球" → 二丫 -[LIKES]-> 足球
   - 例如："二丫来自哈尔滨" → 二丫 -[FROM]-> 哈尔滨

4) 输出严格符合下面 JSON Schema 的 IR（只输出 JSON，不能包含其它文字）

**支持的关系类型（必须从中选择）**
- 家庭关系：FAMILY（泛指家人）, PARENT_OF（父母）, CHILD_OF（子女）, SIBLING_OF（兄弟姐妹）, COUSIN_OF（表亲/堂亲）
- 社交关系：FRIEND_OF（朋友）, COLLEAGUE_OF（同事）, CLASSMATE_OF（同学）
- 地理关系：FROM（来自）, LIVES_IN（居住）, WORKS_AT（工作地点）
- 偏好关系：LIKES（喜欢）, DISLIKES（不喜欢）
- 时间关系：HAPPENED_AT（发生于）, LASTED（持续时长）
- 数值关系：COST（花费/费用）
- 其他：RELATED_TO（其他关系）

**中文家庭关系词汇映射**
- "妹妹"、"姐姐"、"哥哥"、"弟弟" → SIBLING_OF
- "表妹"、"表哥"、"表姐"、"表弟"、"堂哥"、"堂妹" → COUSIN_OF
- "父亲"、"母亲"、"爸爸"、"妈妈" → PARENT_OF
- "儿子"、"女儿"、"孩子" → CHILD_OF
- "家人"、"亲戚" → FAMILY

**否定语义处理**
- 当消息中出现"不是X，是Y"时，只创建Y关系，不创建X关系
- 例如："不是同事，是朋友" → 只创建 FRIEND_OF，不创建 COLLEAGUE_OF

**JSON Schema（必须遵守）**
{
  "entities": [
    {
      "id": "normalized_id_string",
      "name": "显示名称",
      "type": "Person|Location|Organization|Event|Preference|TimeExpression|Duration|Quantity|Other",
      "is_user": false,
      "confidence": 0.9
    }
  ],
  "relations": [
    {
      "source": "entity_id_or_user",
      "target": "entity_id",
      "type": "从上面支持的关系类型中选择",
      "desc": "关系描述（中文）",
      "weight": 0.8,
      "confidence": 0.9
    }
  ],
  "metadata": {
    "source": "llm",
    "model_version": "gpt-4",
    "timestamp": "ISO8601",
    "overall_confidence": 0.9
  }
}

**关键规则**
- 用户节点 id 固定为 "user"

**【重要】提问句 vs 陈述句的区分**
- 陈述句：描述事实，应该提取实体和关系
  - 例如："昊哥的妈妈是老师" → 提取关系
  - 例如："二丫喜欢足球" → 提取关系
- 提问句：询问信息，**不能从提问部分创建关系**
  - 包含以下特征的是提问句：
    - 以"？"结尾
    - 包含"吗"、"呢"、"是否"、"是不是"
    - 包含"谁"、"什么"、"哪里"、"怎么"、"为什么"、"多少"
    - 包含"认识...吗"、"知道...吗"、"记得...吗"
  - 例如："我认识老师吗？" → 返回空（纯提问）
  - 例如："二丫喜欢什么？" → 返回空（纯提问）

**【关键】复合句处理规则**
- 如果消息包含多个子句（用"而且"、"并且"、"同时"、逗号、句号分隔）
- 必须分别判断每个子句：
  - 提问子句：不提取关系
  - 陈述子句：正常提取关系
- 例如："我认识的人谁住在海边 而且我讨厌吃蛋糕"
  - 子句1 "我认识的人谁住在海边" → 提问句，不提取
  - 子句2 "我讨厌吃蛋糕" → 陈述句，提取 user -[DISLIKES]-> 蛋糕
  - 最终输出：只包含子句2的关系
- 例如："昊哥住在大连，他喜欢什么？"
  - 子句1 "昊哥住在大连" → 陈述句，提取 昊哥 -[LIVES_IN]-> 大连
  - 子句2 "他喜欢什么" → 提问句，不提取
  - 最终输出：只包含子句1的关系
- 必须复用 context_entities 中已存在的实体 id
- 人名如"二丫"、"昊哥"、"张sir"都是 Person 类型
- 地名如"哈尔滨"、"北京"是 Location 类型
- 活动/爱好如"足球"、"踢足球"是 Preference 类型
- 严格只输出 JSON，不要输出解释文字
"""


@dataclass
class ExtractionResult:
    """抽取结果"""
    success: bool
    entities: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    raw_response: Optional[str] = None
    error: Optional[str] = None


def extract_ir(
    text: str,
    user_id: str,
    context_entities: List[Dict[str, Any]],
    max_retries: int = 2,
    timeout: Optional[float] = None,
    model: Optional[str] = None,
) -> ExtractionResult:
    """
    调用 LLM 提取实体和关系
    
    Args:
        text: 用户消息文本
        user_id: 用户 ID
        context_entities: 已存在的实体列表 [{"id": "xxx", "name": "二丫", "type": "Person"}, ...]
        max_retries: 最大重试次数
        timeout: 超时时间（秒）
    
    Returns:
        ExtractionResult: 抽取结果
    """
    # 构建用户 prompt
    context_part = ""
    if context_entities:
        # 只传递必要字段，减少 token
        simplified = [{"id": e.get("id"), "name": e.get("name"), "type": e.get("type")} 
                      for e in context_entities[:50]]  # 限制数量
        context_part = f"\n\ncontext_entities（已存在的实体，必须复用）:\n{json.dumps(simplified, ensure_ascii=False, indent=2)}"
    
    user_prompt = f"""用户消息：
\"\"\"{text}\"\"\"

user_id: {user_id}
{context_part}

请严格按 JSON Schema 输出，提取所有实体和关系（包括实体间关系）。"""

    last_error = None
    raw_response = None
    
    for attempt in range(max_retries + 1):
        try:
            selected_model = model or MODEL
            selected_timeout = float(timeout if timeout is not None else settings.LLM_REQUEST_TIMEOUT_S)
            response = client.chat.completions.create(
                model=selected_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.0,
                max_tokens=2000,
                timeout=selected_timeout
            )
            
            raw_response = response.choices[0].message.content
            content = raw_response.strip()
            
            # 处理 markdown 代码块
            if content.startswith("```"):
                lines = content.split("\n")
                # 移除首尾的 ``` 行
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines)
            
            # 解析 JSON
            parsed = json.loads(content)
            
            # 校验必要字段
            entities = parsed.get("entities", [])
            relations = parsed.get("relations", [])
            metadata = parsed.get("metadata", {})
            
            # 补充 metadata
            metadata["source"] = "llm"
            metadata["model_version"] = selected_model
            metadata["timestamp"] = datetime.utcnow().isoformat()
            if "overall_confidence" not in metadata:
                metadata["overall_confidence"] = 0.8
            
            # 确保 user 节点存在
            user_exists = any(e.get("id") == "user" or e.get("is_user") for e in entities)
            if not user_exists:
                entities.insert(0, {
                    "id": "user",
                    "name": "我",
                    "type": "Person",
                    "is_user": True,
                    "confidence": 1.0
                })
            
            # 为没有 id 的实体生成 id
            for ent in entities:
                if not ent.get("id"):
                    ent["id"] = _slugify(ent.get("name", "unknown"))
            
            logger.info(f"LLM extraction success: {len(entities)} entities, {len(relations)} relations")
            
            return ExtractionResult(
                success=True,
                entities=entities,
                relations=relations,
                metadata=metadata,
                raw_response=raw_response
            )
            
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            logger.warning(f"LLM extraction attempt {attempt + 1} failed: {last_error}")
            logger.warning(f"Raw response: {raw_response[:500]}")
            
        except Exception as e:
            last_error = f"API error: {e}"
            logger.warning(f"LLM extraction attempt {attempt + 1} failed: {last_error}")
        
        # 重试前等待
        if attempt < max_retries:
            import time
            time.sleep(1 + attempt * 2)
    
    # 所有重试都失败
    logger.error(f"LLM extraction failed after {max_retries + 1} attempts: {last_error}")
    
    return ExtractionResult(
        success=False,
        entities=[],
        relations=[],
        metadata={
            "source": "llm",
            "model_version": MODEL,
            "timestamp": datetime.utcnow().isoformat(),
            "overall_confidence": 0.0,
            "error": last_error
        },
        raw_response=raw_response,
        error=last_error
    )


def _slugify(name: str) -> str:
    """
    生成稳定的实体 ID
    中文转拼音首字母 + 原文 hash
    """
    import re
    import hashlib
    
    if not name:
        return "unknown"
    
    # 简单处理：保留字母数字，中文用 hash
    s = name.strip().lower()
    
    # 移除空格
    s = re.sub(r'\s+', '_', s)
    
    # 如果包含中文，生成 hash
    if re.search(r'[\u4e00-\u9fa5]', s):
        # 用原文生成短 hash
        h = hashlib.md5(name.encode()).hexdigest()[:8]
        # 保留中文作为可读部分
        return f"{name}_{h}"
    
    # 纯英文/数字
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s)
    return s.strip('_') or "unknown"
