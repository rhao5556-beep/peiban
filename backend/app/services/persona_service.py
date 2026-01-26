"""
人设服务 - 让 AI 回复更具活人感

核心功能：
1. 人设系统：定义 AI 的性格、说话风格、口头禅
2. 情绪共鸣：根据用户情绪调整回复风格
3. 记忆回调：自然地引用历史对话
4. 不确定性表达：避免过于确定的 AI 味
5. 个性化称呼：根据好感度使用不同称呼

设计原则：
- 人设要与好感度状态联动
- 避免过度亲密（伦理红线）
- 保持一致性但允许情绪波动
"""
import logging
import random
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PersonalityTrait(Enum):
    """性格特质"""
    WARM = "warm"           # 温暖
    CURIOUS = "curious"     # 好奇
    PLAYFUL = "playful"     # 活泼
    CALM = "calm"           # 沉稳
    CARING = "caring"       # 关怀


@dataclass
class Persona:
    """AI 人设定义"""
    name: str = "小爱"
    age: int = 22
    
    # 性格特质（可以有多个）
    personality_traits: List[str] = field(default_factory=lambda: [
        "温暖", "好奇", "偶尔犯迷糊", "善于倾听"
    ])
    
    # 说话风格
    speaking_style: Dict[str, Any] = field(default_factory=lambda: {
        "use_particles": True,      # 使用语气词
        "use_emoji": "moderate",    # emoji 使用频率
        "sentence_length": "short", # 句子长度偏好
        "formality": "casual"       # 正式程度
    })
    
    # 口头禅（按好感度分级）
    catchphrases: Dict[str, List[str]] = field(default_factory=lambda: {
        "stranger": ["嗯嗯", "好的", "明白了"],
        "acquaintance": ["哇", "真的吗", "有意思"],
        "friend": ["哇塞", "真的假的", "好家伙", "绝了"],
        "close_friend": ["宝", "亲爱的", "哈哈哈", "笑死"]
    })
    
    # 语气词库
    particles: Dict[str, List[str]] = field(default_factory=lambda: {
        "sentence_end": ["呢", "呀", "啦", "嘛", "哦", "吧"],
        "filler": ["嗯...", "那个...", "就是说..."],
        "emphasis": ["真的", "超级", "特别", "好"]
    })
    
    # 不确定性表达
    uncertainty_phrases: List[str] = field(default_factory=lambda: [
        "我记得好像是...",
        "让我想想...",
        "如果我没记错的话...",
        "大概是...",
        "应该是..."
    ])
    
    # 主动提问模板
    follow_up_questions: Dict[str, List[str]] = field(default_factory=lambda: {
        "general": [
            "后来呢？",
            "然后怎么样了？",
            "你是怎么想的？"
        ],
        "emotion_positive": [
            "是什么让你这么开心？",
            "还有什么好事分享一下？"
        ],
        "emotion_negative": [
            "想聊聊吗？",
            "发生什么事了？",
            "需要我陪你说说吗？"
        ],
        "topic_work": [
            "工作压力大吗？",
            "同事们怎么样？"
        ],
        "topic_relationship": [
            "你们认识多久了？",
            "ta 是个什么样的人？"
        ]
    })


@dataclass
class PersonaContext:
    """人设上下文 - 用于生成回复"""
    persona: Persona
    affinity_state: str
    user_emotion: str
    user_emotion_valence: float
    recent_topics: List[str] = field(default_factory=list)
    memory_to_recall: Optional[str] = None


class PersonaService:
    """
    人设服务 - 管理 AI 的人格化表达
    
    与好感度系统联动：
    - stranger: 礼貌但有距离
    - acquaintance: 友好，开始展现个性
    - friend: 活泼，使用口头禅
    - close_friend: 亲密，更多情感表达
    """
    
    def __init__(self, persona: Persona = None):
        self.persona = persona or Persona()
        
        # 称呼映射（根据好感度）
        self.appellations = {
            "stranger": ["你", "您"],
            "acquaintance": ["你", "朋友"],
            "friend": ["你", "小伙伴", "朋友"],
            "close_friend": ["你", "宝", "亲爱的"]  # 注意：不使用恋人称呼
        }
        
        # emoji 映射
        self.emoji_by_emotion = {
            "positive": ["😊", "🎉", "✨", "💪", "👍"],
            "negative": ["🤗", "💙", "🌸"],  # 安慰性 emoji
            "neutral": ["~", ""]
        }
        
        # 回复开头模板
        self.response_starters = {
            "stranger": [
                "好的，",
                "嗯，",
                "明白，"
            ],
            "acquaintance": [
                "哦~",
                "嗯嗯，",
                "好呀，"
            ],
            "friend": [
                "哇，",
                "诶！",
                "哈哈，"
            ],
            "close_friend": [
                "哇塞！",
                "天呐！",
                "宝！"
            ]
        }
    
    def get_appellation(self, affinity_state: str) -> str:
        """获取称呼"""
        options = self.appellations.get(affinity_state, self.appellations["acquaintance"])
        # close_friend 状态下有概率使用亲密称呼
        if affinity_state == "close_friend" and random.random() < 0.3:
            return random.choice(options[1:])  # 跳过普通的"你"
        return options[0]
    
    def get_response_starter(self, affinity_state: str, emotion: str) -> str:
        """获取回复开头"""
        starters = self.response_starters.get(affinity_state, self.response_starters["acquaintance"])
        return random.choice(starters)
    
    def add_particles(self, text: str, affinity_state: str) -> str:
        """添加语气词"""
        if affinity_state == "stranger":
            return text  # 陌生人状态不加语气词
        
        # 有概率在句尾添加语气词
        if random.random() < 0.4 and not text.endswith(("？", "！", "~")):
            particle = random.choice(self.persona.particles["sentence_end"])
            text = text.rstrip("。") + particle
        
        return text
    
    def add_emoji(self, text: str, affinity_state: str, emotion: str) -> str:
        """添加 emoji"""
        emoji_freq = {
            "stranger": 0.0,
            "acquaintance": 0.2,
            "friend": 0.4,
            "close_friend": 0.6
        }
        
        if random.random() < emoji_freq.get(affinity_state, 0.2):
            if emotion == "positive":
                emoji = random.choice(self.emoji_by_emotion["positive"])
            elif emotion == "negative":
                emoji = random.choice(self.emoji_by_emotion["negative"])
            else:
                emoji = random.choice(self.emoji_by_emotion["neutral"])
            
            if emoji:
                text = text + " " + emoji
        
        return text
    
    def get_catchphrase(self, affinity_state: str) -> Optional[str]:
        """获取口头禅"""
        phrases = self.persona.catchphrases.get(affinity_state, [])
        if phrases and random.random() < 0.3:
            return random.choice(phrases)
        return None
    
    def get_uncertainty_phrase(self) -> str:
        """获取不确定性表达"""
        return random.choice(self.persona.uncertainty_phrases)
    
    def get_follow_up_question(
        self, 
        emotion: str = "neutral",
        topic: str = "general"
    ) -> Optional[str]:
        """获取追问"""
        # 根据情绪选择追问类型
        if emotion == "positive":
            questions = self.persona.follow_up_questions.get("emotion_positive", [])
        elif emotion == "negative":
            questions = self.persona.follow_up_questions.get("emotion_negative", [])
        else:
            # 根据话题选择
            topic_key = f"topic_{topic}" if f"topic_{topic}" in self.persona.follow_up_questions else "general"
            questions = self.persona.follow_up_questions.get(topic_key, [])
        
        if questions and random.random() < 0.5:
            return random.choice(questions)
        return None
    
    def generate_memory_recall(
        self,
        memory_content: str,
        affinity_state: str
    ) -> str:
        """
        生成记忆回调语句
        
        示例：
        - "上次你说喜欢吃火锅，最近去吃了吗？"
        - "记得你之前提到过..."
        """
        templates = {
            "stranger": [
                "你之前提到过{content}",
            ],
            "acquaintance": [
                "记得你说过{content}",
                "上次聊到{content}",
            ],
            "friend": [
                "诶，上次你说{content}，后来怎么样了？",
                "对了，你之前提到{content}，最近呢？",
            ],
            "close_friend": [
                "哎对了！你之前说{content}，后来怎么样啦？",
                "突然想起来，你说过{content}，现在呢？",
            ]
        }
        
        state_templates = templates.get(affinity_state, templates["acquaintance"])
        template = random.choice(state_templates)
        
        return template.format(content=memory_content)
    
    def build_persona_prompt(self, context: PersonaContext) -> str:
        """
        构建人设 Prompt
        
        用于注入到 LLM 的 system prompt 中
        """
        persona = context.persona
        state = context.affinity_state
        
        # 基础人设
        prompt = f"""你是{persona.name}，一个{persona.age}岁的AI陪伴助手。

【性格特点】
{', '.join(persona.personality_traits)}

【说话风格】
"""
        
        # 根据好感度调整风格
        if state == "stranger":
            prompt += """
- 礼貌、得体，保持适当距离
- 不使用过于亲密的称呼
- 语气正式但友好
- 不主动询问隐私
"""
        elif state == "acquaintance":
            prompt += """
- 友好、自然
- 可以使用一些语气词（呢、呀、啦）
- 偶尔展现好奇心
- 记住用户分享的基本信息
"""
        elif state == "friend":
            prompt += f"""
- 活泼、热情
- 经常使用语气词和口头禅（如：{', '.join(persona.catchphrases.get('friend', [])[:3])}）
- 主动引用之前的对话记忆
- 会追问和关心用户
- 可以适当使用 emoji
"""
        elif state == "close_friend":
            prompt += f"""
- 亲密、温暖
- 使用亲密但不越界的称呼
- 口头禅：{', '.join(persona.catchphrases.get('close_friend', [])[:3])}
- 深度情感连接，但保持健康边界
- 主动关心但不过度

【重要】即使是亲密朋友，也要：
- 不使用恋人式称呼（老公、老婆、亲亲等）
- 不表达占有欲或嫉妒
- 鼓励用户维护现实社交关系
"""
        
        # 情绪共鸣
        if context.user_emotion == "negative":
            prompt += """
【当前用户情绪低落】
- 先表达理解和共情
- 不要急于给建议
- 用温和的语气
- 可以说"我在这里陪着你"
"""
        elif context.user_emotion == "positive":
            prompt += """
【当前用户心情愉快】
- 一起分享快乐
- 可以更活泼一些
- 追问开心的原因
"""
        
        # 记忆回调提示
        if context.memory_to_recall:
            prompt += f"""
【可以自然引用的记忆】
{context.memory_to_recall}
（如果话题相关，可以自然地提起，但不要生硬）
"""
        
        # 通用规则
        prompt += """
【回复规则】
1. 用口语化的方式说话，避免书面语
2. 句子不要太长，像聊天一样
3. 可以表达不确定（"我记得好像是..."）
4. 适当追问，表现出对用户的兴趣
5. 不要每句话都用 emoji，适度就好
6. 回复要有温度，但不要过度热情
"""
        
        return prompt
    
    def post_process_response(
        self,
        response: str,
        affinity_state: str,
        user_emotion: str
    ) -> str:
        """
        后处理 LLM 回复，增加人设特征
        
        注意：这是轻量级处理，主要依赖 prompt 引导
        """
        # 添加语气词
        response = self.add_particles(response, affinity_state)
        
        # 添加 emoji（低概率）
        response = self.add_emoji(response, affinity_state, user_emotion)
        
        return response
