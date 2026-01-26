"""
优化版对话服务 - 更自然的 Prompt 工程

核心改进：
1. 简化 Prompt 结构
2. 自然语言化检索结果
3. 添加 Few-shot 示例
4. 减少硬性规则
"""

def build_optimized_prompt(
    message: str,
    memories: list,
    graph_facts: list,
    conversation_history: list,
    affinity_score: float,
    affinity_state: str
) -> str:
    """
    构建优化的 Prompt
    
    关键改进：
    - 用自然语言描述记忆，而不是结构化数据
    - 减少规则，增加示例
    - 让 LLM 自由发挥
    """
    
    # 1. 将记忆转换为自然语言
    memory_context = _format_memories_naturally(memories, graph_facts)
    
    # 2. 格式化对话历史
    history_context = _format_history_naturally(conversation_history)
    
    # 3. 根据好感度调整语气提示
    tone_hint = _get_tone_hint(affinity_score, affinity_state)
    
    # 4. 构建简洁的 Prompt
    prompt = f"""你是 Affinity，一个温暖、善解人意的 AI 陪伴助手。

## 你对用户的了解

{memory_context}

## 最近的对话

{history_context}

## 当前对话

用户: {message}

## 回复指南

{tone_hint}

请自然、真诚地回复用户。如果不确定某些信息，可以坦诚说不记得，并询问用户。

---

## 示例对话（参考风格）

用户: 我和二丫去沈阳溜达过一圈 但是昊哥和张sir没去
Affinity: 听起来那次沈阳之行应该挺有趣的！二丫和你一起肯定玩得很开心。昊哥和张sir下次有机会也会想去看看吧，毕竟他们也是你们的朋友，分享彼此的经历是很棒的事情。有没有什么特别的记忆想要呢？

用户: 谁去沈阳旅游过
Affinity: 根据你之前告诉我的，你和二丫一起去过沈阳旅游。那次是你们两个人的行程，昊哥和张sir没有参加。

---

现在请回复用户的消息："""
    
    return prompt


def _format_memories_naturally(memories: list, graph_facts: list) -> str:
    """
    将检索结果转换为自然语言叙述
    
    改进前：
    - Entity: 二丫 (Person)
    - Relation: USER -> FRIEND_OF -> 二丫
    
    改进后：
    - 二丫是你的朋友
    - 你和二丫一起去过沈阳旅游
    """
    if not memories and not graph_facts:
        return "（你还没有告诉我太多关于你的事情）"
    
    context_parts = []
    
    # 处理图谱事实（关系）
    if graph_facts:
        # 按人物分组
        people_facts = {}
        for fact in graph_facts:
            entity_name = fact.get("entity_name", "")
            if entity_name not in people_facts:
                people_facts[entity_name] = []
            people_facts[entity_name].append(fact)
        
        # 为每个人物生成自然语言描述
        for person, facts in people_facts.items():
            person_desc = f"关于{person}："
            fact_descs = []
            
            for fact in facts:
                rel_type = fact.get("relation_type", "")
                rel_desc = fact.get("relation_desc", "")
                
                if rel_type == "FRIEND_OF":
                    fact_descs.append(f"是你的朋友")
                elif rel_type == "COUSIN_OF":
                    fact_descs.append(f"是你的表亲")
                elif rel_type == "LIVES_IN":
                    location = fact.get("target_name", "")
                    fact_descs.append(f"住在{location}")
                elif rel_type == "WORKS_AT":
                    place = fact.get("target_name", "")
                    fact_descs.append(f"在{place}工作")
                elif rel_desc:
                    fact_descs.append(rel_desc)
            
            if fact_descs:
                person_desc += "、".join(fact_descs)
                context_parts.append(person_desc)
    
    # 处理向量检索的对话记忆
    if memories:
        context_parts.append("\n你之前还提到过：")
        for mem in memories[:3]:  # 只取前3条最相关的
            content = mem.get("content", "")
            if content:
                context_parts.append(f"- {content}")
    
    return "\n".join(context_parts) if context_parts else "（暂无相关记忆）"


def _format_history_naturally(conversation_history: list) -> str:
    """
    自然格式化对话历史
    """
    if not conversation_history:
        return "（这是你们的第一次对话）"
    
    history_lines = []
    for turn in conversation_history[-3:]:  # 只取最近3轮
        user_msg = turn.get("user_message", "")
        ai_reply = turn.get("ai_reply", "")
        
        if user_msg:
            history_lines.append(f"用户: {user_msg}")
        if ai_reply:
            history_lines.append(f"Affinity: {ai_reply}")
    
    return "\n".join(history_lines)


def _get_tone_hint(affinity_score: float, affinity_state: str) -> str:
    """
    根据好感度给出语气提示
    """
    if affinity_score >= 0.7:
        return "你们是很亲密的朋友，可以用轻松、亲切的语气，偶尔开开玩笑。"
    elif affinity_score >= 0.4:
        return "你们是朋友，用友好、温暖的语气交流。"
    else:
        return "你们还不太熟，保持礼貌、友善的语气。"
