"""用户画像服务 - 聚合用户特征和偏好"""
import logging
import json
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_neo4j_driver

logger = logging.getLogger(__name__)


@dataclass
class PersonalityTraits:
    """性格特征"""
    introvert_extrovert: float = 0.0  # -1 (introvert) to 1 (extrovert)
    optimist_pessimist: float = 0.0   # -1 (pessimist) to 1 (optimist)
    analytical_emotional: float = 0.0  # -1 (analytical) to 1 (emotional)
    confidence: float = 0.0  # 置信度


@dataclass
class CommunicationStyle:
    """沟通风格"""
    avg_message_length: float = 0.0
    emoji_frequency: float = 0.0  # 0-1
    question_frequency: float = 0.0  # 0-1
    response_speed_preference: str = "moderate"  # fast, moderate, thoughtful


@dataclass
class Interest:
    """兴趣偏好"""
    name: str
    category: str  # hobby, food, place, person, etc.
    sentiment: str  # like, dislike
    weight: float = 0.5
    last_mentioned: Optional[datetime] = None


@dataclass
class UserProfile:
    """用户画像"""
    user_id: str
    personality: PersonalityTraits = field(default_factory=PersonalityTraits)
    interests: List[Interest] = field(default_factory=list)
    communication_style: CommunicationStyle = field(default_factory=CommunicationStyle)
    active_hours: List[int] = field(default_factory=list)  # 0-23
    topic_preferences: Dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def staleness_days(self) -> int:
        """计算画像陈旧天数"""
        return (datetime.now() - self.updated_at).days
    
    @property
    def is_stale(self) -> bool:
        """判断画像是否陈旧（超过30天未更新）"""
        return self.staleness_days > 30
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "personality": asdict(self.personality),
            "interests": [asdict(i) if hasattr(i, '__dataclass_fields__') else i for i in self.interests],
            "communication_style": asdict(self.communication_style),
            "active_hours": self.active_hours,
            "topic_preferences": self.topic_preferences,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "staleness_days": self.staleness_days,
            "is_stale": self.is_stale
        }


@dataclass
class ProfileUpdateSignals:
    """画像更新信号"""
    message_length: Optional[int] = None
    has_emoji: bool = False
    has_question: bool = False
    emotion_valence: float = 0.0
    topics_mentioned: List[str] = field(default_factory=list)
    hour_of_day: Optional[int] = None


class UserProfileService:
    """
    用户画像服务 - 聚合用户特征
    
    Property 10: User Profile Completeness
    Property 12: Profile Staleness Detection
    """
    
    def __init__(self, db_session: AsyncSession = None, neo4j_driver=None):
        self.db = db_session
        self.neo4j = neo4j_driver or get_neo4j_driver()
    
    async def get_profile(self, user_id: str) -> UserProfile:
        """
        获取用户画像（懒创建）
        
        如果画像不存在，创建默认画像
        """
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    text("""
                        SELECT user_id, introvert_extrovert, optimist_pessimist,
                               analytical_emotional, personality_confidence,
                               avg_message_length, emoji_frequency, question_frequency,
                               response_speed_preference, active_hours, topic_preferences,
                               created_at, updated_at
                        FROM user_profiles
                        WHERE user_id = :user_id
                    """),
                    {"user_id": user_id}
                )
                row = result.fetchone()
                
                if row:
                    # 解析数据库记录
                    personality = PersonalityTraits(
                        introvert_extrovert=row[1] or 0.0,
                        optimist_pessimist=row[2] or 0.0,
                        analytical_emotional=row[3] or 0.0,
                        confidence=row[4] or 0.0
                    )
                    
                    communication_style = CommunicationStyle(
                        avg_message_length=row[5] or 0.0,
                        emoji_frequency=row[6] or 0.0,
                        question_frequency=row[7] or 0.0,
                        response_speed_preference=row[8] or "moderate"
                    )
                    
                    active_hours = row[9] if row[9] else []
                    topic_preferences = row[10] if row[10] else {}
                    
                    # 获取兴趣偏好
                    interests = await self.get_interests(user_id)
                    
                    return UserProfile(
                        user_id=user_id,
                        personality=personality,
                        interests=interests,
                        communication_style=communication_style,
                        active_hours=active_hours,
                        topic_preferences=topic_preferences,
                        created_at=row[11] or datetime.now(),
                        updated_at=row[12] or datetime.now()
                    )
                else:
                    # 创建默认画像
                    return await self._create_default_profile(user_id)
                    
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            # 返回默认画像
            return UserProfile(user_id=user_id)

    async def _create_default_profile(self, user_id: str) -> UserProfile:
        """创建默认用户画像"""
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text("""
                        INSERT INTO user_profiles (user_id, created_at, updated_at)
                        VALUES (:user_id, NOW(), NOW())
                        ON CONFLICT (user_id) DO NOTHING
                    """),
                    {"user_id": user_id}
                )
                await db.commit()
                
            logger.info(f"Created default profile for user {user_id}")
            return UserProfile(user_id=user_id)
            
        except Exception as e:
            logger.error(f"Failed to create default profile: {e}")
            return UserProfile(user_id=user_id)
    
    async def update_profile(
        self,
        user_id: str,
        signals: ProfileUpdateSignals
    ) -> UserProfile:
        """
        增量更新用户画像
        
        基于对话信号更新画像维度
        """
        try:
            # 获取当前画像
            profile = await self.get_profile(user_id)
            
            # 更新沟通风格
            if signals.message_length is not None:
                # 指数移动平均更新消息长度
                alpha = 0.1
                profile.communication_style.avg_message_length = (
                    alpha * signals.message_length +
                    (1 - alpha) * profile.communication_style.avg_message_length
                )
            
            if signals.has_emoji:
                profile.communication_style.emoji_frequency = min(
                    1.0,
                    profile.communication_style.emoji_frequency + 0.05
                )
            
            if signals.has_question:
                profile.communication_style.question_frequency = min(
                    1.0,
                    profile.communication_style.question_frequency + 0.05
                )
            
            # 更新性格特征（基于情感）
            if signals.emotion_valence != 0:
                alpha = 0.05
                profile.personality.optimist_pessimist = max(-1, min(1,
                    profile.personality.optimist_pessimist + alpha * signals.emotion_valence
                ))
                profile.personality.confidence = min(1.0, profile.personality.confidence + 0.01)
            
            # 更新活跃时间
            if signals.hour_of_day is not None:
                if signals.hour_of_day not in profile.active_hours:
                    profile.active_hours.append(signals.hour_of_day)
                    profile.active_hours = sorted(profile.active_hours)[-10:]  # 保留最近10个
            
            # 更新话题偏好
            for topic in signals.topics_mentioned:
                current = profile.topic_preferences.get(topic, 0.0)
                profile.topic_preferences[topic] = min(1.0, current + 0.1)
            
            # 保存到数据库
            await self._save_profile(profile)
            
            return profile
            
        except Exception as e:
            logger.error(f"Failed to update profile: {e}")
            return await self.get_profile(user_id)
    
    async def _save_profile(self, profile: UserProfile) -> None:
        """保存画像到数据库"""
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text("""
                        UPDATE user_profiles SET
                            introvert_extrovert = :ie,
                            optimist_pessimist = :op,
                            analytical_emotional = :ae,
                            personality_confidence = :pc,
                            avg_message_length = :aml,
                            emoji_frequency = :ef,
                            question_frequency = :qf,
                            response_speed_preference = :rsp,
                            active_hours = :ah,
                            topic_preferences = :tp,
                            updated_at = NOW()
                        WHERE user_id = :user_id
                    """),
                    {
                        "user_id": profile.user_id,
                        "ie": profile.personality.introvert_extrovert,
                        "op": profile.personality.optimist_pessimist,
                        "ae": profile.personality.analytical_emotional,
                        "pc": profile.personality.confidence,
                        "aml": profile.communication_style.avg_message_length,
                        "ef": profile.communication_style.emoji_frequency,
                        "qf": profile.communication_style.question_frequency,
                        "rsp": profile.communication_style.response_speed_preference,
                        "ah": json.dumps(profile.active_hours),
                        "tp": json.dumps(profile.topic_preferences)
                    }
                )
                await db.commit()
                
        except Exception as e:
            logger.error(f"Failed to save profile: {e}")
    
    async def analyze_personality(
        self,
        user_id: str,
        recent_messages: List[str]
    ) -> PersonalityTraits:
        """
        分析性格特征（基于消息模式）
        
        使用简单的规则分析，未来可以接入 LLM
        """
        if not recent_messages:
            return PersonalityTraits()
        
        # 统计特征
        total_length = sum(len(m) for m in recent_messages)
        avg_length = total_length / len(recent_messages)
        
        # 情感词统计
        positive_words = ["开心", "高兴", "喜欢", "爱", "棒", "好", "哈哈", "嘻嘻", "😊", "😄"]
        negative_words = ["难过", "伤心", "讨厌", "烦", "累", "不好", "😢", "😞"]
        question_marks = sum(m.count("?") + m.count("？") for m in recent_messages)
        exclamation_marks = sum(m.count("!") + m.count("！") for m in recent_messages)
        
        positive_count = sum(
            sum(1 for w in positive_words if w in m)
            for m in recent_messages
        )
        negative_count = sum(
            sum(1 for w in negative_words if w in m)
            for m in recent_messages
        )
        
        # 计算性格维度
        # 外向性：消息长度 + 感叹号使用
        extrovert_score = min(1, max(-1, (avg_length - 20) / 50 + exclamation_marks * 0.1))
        
        # 乐观性：正面词 vs 负面词
        total_sentiment = positive_count + negative_count
        if total_sentiment > 0:
            optimist_score = (positive_count - negative_count) / total_sentiment
        else:
            optimist_score = 0.0
        
        # 分析性：问号使用
        analytical_score = min(1, -question_marks * 0.1)  # 多问问题 -> 更分析型
        
        # 置信度：基于消息数量
        confidence = min(1.0, len(recent_messages) / 20)
        
        return PersonalityTraits(
            introvert_extrovert=extrovert_score,
            optimist_pessimist=optimist_score,
            analytical_emotional=analytical_score,
            confidence=confidence
        )
    
    async def get_interests(self, user_id: str) -> List[Interest]:
        """
        从 Neo4j 图谱提取兴趣偏好
        
        查询 LIKES 和 DISLIKES 关系
        """
        interests = []
        
        if not self.neo4j:
            return interests
        
        try:
            async with self.neo4j.session() as session:
                # 查询 LIKES 关系
                likes_query = """
                MATCH (u:User {id: $user_id})-[r:LIKES]->(target)
                RETURN target.name AS name, labels(target)[0] AS category,
                       coalesce(r.weight, 0.5) AS weight
                LIMIT 50
                """
                result = await session.run(likes_query, user_id=user_id)
                
                async for record in result:
                    interests.append(Interest(
                        name=record["name"],
                        category=record["category"] or "unknown",
                        sentiment="like",
                        weight=record["weight"]
                    ))
                
                # 查询 DISLIKES 关系
                dislikes_query = """
                MATCH (u:User {id: $user_id})-[r:DISLIKES]->(target)
                RETURN target.name AS name, labels(target)[0] AS category,
                       coalesce(r.weight, 0.5) AS weight
                LIMIT 50
                """
                result = await session.run(dislikes_query, user_id=user_id)
                
                async for record in result:
                    interests.append(Interest(
                        name=record["name"],
                        category=record["category"] or "unknown",
                        sentiment="dislike",
                        weight=record["weight"]
                    ))
                
        except Exception as e:
            logger.error(f"Failed to get interests from Neo4j: {e}")
        
        return interests
    
    async def get_communication_style(self, user_id: str) -> CommunicationStyle:
        """
        分析沟通风格（基于消息统计）
        """
        try:
            async with AsyncSessionLocal() as db:
                # 统计消息特征
                result = await db.execute(
                    text("""
                        SELECT 
                            AVG(LENGTH(content)) AS avg_length,
                            COUNT(*) AS total_messages
                        FROM memories
                        WHERE user_id = :user_id
                        AND created_at > NOW() - INTERVAL '30 days'
                    """),
                    {"user_id": user_id}
                )
                row = result.fetchone()
                
                if row and row[0]:
                    avg_length = float(row[0])
                    
                    # 根据平均长度推断响应速度偏好
                    if avg_length < 20:
                        speed_pref = "fast"
                    elif avg_length < 50:
                        speed_pref = "moderate"
                    else:
                        speed_pref = "thoughtful"
                    
                    return CommunicationStyle(
                        avg_message_length=avg_length,
                        response_speed_preference=speed_pref
                    )
                
        except Exception as e:
            logger.error(f"Failed to analyze communication style: {e}")
        
        return CommunicationStyle()
    
    async def get_stale_profiles(self, days: int = 30) -> List[str]:
        """
        获取陈旧的用户画像列表
        
        用于定期更新任务
        """
        stale_user_ids = []
        
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    text("""
                        SELECT user_id
                        FROM user_profiles
                        WHERE updated_at < NOW() - INTERVAL ':days days'
                    """.replace(":days", str(days)))
                )
                rows = result.fetchall()
                stale_user_ids = [row[0] for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get stale profiles: {e}")
        
        return stale_user_ids
