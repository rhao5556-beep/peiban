"""
主动对话服务 - 让 AI 像真人一样主动发消息

核心模块：
1. TriggerEngine - 触发引擎
2. MessageGenerator - 消息生成器
3. DeliveryManager - 推送管理
4. FeedbackTracker - 反馈追踪

设计原则：
- 主动消息是服务，不是骚扰
- 用户可以随时关闭
- 频率要克制
- 文案要自然，不能有情感勒索
- 与好感度系统联动
"""
import logging
import uuid
from datetime import datetime, timedelta, time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo
import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ==================== 枚举定义 ====================

class TriggerType(Enum):
    """触发类型"""
    TIME = "time"           # 时间触发（早安、晚安）
    SILENCE = "silence"     # 沉默触发（用户N天未互动）
    DECAY = "decay"         # 衰减触发（重要关系即将遗忘）
    EVENT = "event"         # 事件触发（生日、纪念日）
    WEATHER = "weather"     # 天气触发（极端天气关怀）
    EMOTION = "emotion"     # 情绪触发（上次对话情绪低落）


class MessageStatus(Enum):
    """消息状态"""
    PENDING = "pending"     # 待发送
    SENT = "sent"           # 已发送
    DELIVERED = "delivered" # 已送达
    READ = "read"           # 已读
    CANCELLED = "cancelled" # 已取消
    IGNORED = "ignored"     # 被忽略（用户未回复）


class UserResponse(Enum):
    """用户响应类型"""
    REPLIED = "replied"     # 回复了
    IGNORED = "ignored"     # 忽略了
    DISABLED = "disabled"   # 关闭了主动消息


# ==================== 数据类 ====================

@dataclass
class TriggerRule:
    """触发规则"""
    trigger_type: TriggerType
    condition: Dict[str, Any]
    action: str
    priority: int = 5  # 1-10, 10最高
    cooldown_hours: int = 24  # 冷却时间
    min_affinity_state: str = "acquaintance"  # 最低好感度要求
    enabled: bool = True


@dataclass
class ProactiveMessage:
    """主动消息"""
    id: str
    user_id: str
    trigger_type: str
    trigger_rule_id: Optional[str]
    content: str
    scheduled_at: datetime
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    user_response: Optional[str] = None
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserPreference:
    """用户偏好设置"""
    user_id: str
    proactive_enabled: bool = True
    morning_greeting: bool = True
    evening_greeting: bool = False
    silence_reminder: bool = True
    event_reminder: bool = True
    quiet_hours_start: time = time(22, 0)  # 免打扰开始
    quiet_hours_end: time = time(8, 0)     # 免打扰结束
    max_daily_messages: int = 2            # 每日最大主动消息数
    preferred_greeting_time: Optional[time] = None
    timezone: str = "Asia/Shanghai"


# ==================== 触发引擎 ====================

class TriggerEngine:
    """
    触发引擎 - 决定何时发送主动消息
    
    触发类型：
    1. 时间触发：早安、晚安
    2. 沉默触发：用户N天未互动
    3. 衰减触发：重要关系即将遗忘
    4. 事件触发：生日、纪念日
    """
    
    # 默认触发规则
    DEFAULT_RULES: List[TriggerRule] = [
        # 早安问候
        TriggerRule(
            trigger_type=TriggerType.TIME,
            condition={"time": "08:00", "type": "morning"},
            action="morning_greeting",
            priority=3,
            cooldown_hours=24,
            min_affinity_state="acquaintance"
        ),
        # 晚安问候
        TriggerRule(
            trigger_type=TriggerType.TIME,
            condition={"time": "22:00", "type": "evening"},
            action="evening_greeting",
            priority=2,
            cooldown_hours=24,
            min_affinity_state="friend"
        ),
        # 沉默提醒（3天未互动）
        TriggerRule(
            trigger_type=TriggerType.SILENCE,
            condition={"days": 3},
            action="gentle_checkin",
            priority=5,
            cooldown_hours=72,
            min_affinity_state="acquaintance"
        ),
        # 沉默提醒（7天未互动）
        TriggerRule(
            trigger_type=TriggerType.SILENCE,
            condition={"days": 7},
            action="care_message",
            priority=6,
            cooldown_hours=168,
            min_affinity_state="friend"
        ),
        # 生日祝福
        TriggerRule(
            trigger_type=TriggerType.EVENT,
            condition={"event": "birthday"},
            action="birthday_wish",
            priority=10,
            cooldown_hours=8760,  # 一年
            min_affinity_state="acquaintance"
        ),
        # 重要记忆衰减提醒
        TriggerRule(
            trigger_type=TriggerType.DECAY,
            condition={"weight_threshold": 0.5, "importance": "high"},
            action="memory_recall",
            priority=4,
            cooldown_hours=168,
            min_affinity_state="friend"
        ),
    ]
    
    def __init__(self, db_session: AsyncSession = None):
        self.db = db_session
        self.rules = self.DEFAULT_RULES.copy()

    def load_rules_from_config(self, rules_config: Any) -> None:
        rules = _build_trigger_rules_from_dicts(rules_config)
        if rules:
            self.rules = rules
    
    async def check_triggers(
        self,
        user_id: str,
        affinity_state: str,
        user_preference: UserPreference
    ) -> List[TriggerRule]:
        """
        检查所有触发条件，返回满足条件的规则
        """
        if not user_preference.proactive_enabled:
            return []
        
        triggered_rules = []
        now_utc = datetime.utcnow()
        try:
            local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(user_preference.timezone)).replace(tzinfo=None)
        except Exception:
            local_now = now_utc
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            # 检查好感度要求
            if not self._check_affinity_requirement(affinity_state, rule.min_affinity_state):
                continue
            
            # 检查冷却时间
            if await self._is_in_cooldown(user_id, rule, now_utc):
                continue
            
            # 检查免打扰时间
            if self._is_quiet_hours(local_now.time(), user_preference):
                continue
            
            # 检查每日限额
            if await self._exceeded_daily_limit(user_id, user_preference):
                continue
            
            # 检查具体触发条件
            if rule.trigger_type == TriggerType.TIME:
                if self._check_time_condition(rule.condition, local_now):
                    triggered_rules.append(rule)
            else:
                if await self._check_condition(user_id, rule, now_utc):
                    triggered_rules.append(rule)
        
        # 按优先级排序
        triggered_rules.sort(key=lambda r: r.priority, reverse=True)
        
        return triggered_rules
    
    def _check_affinity_requirement(self, current: str, required: str) -> bool:
        """检查好感度是否满足要求"""
        order = ["stranger", "acquaintance", "friend", "close_friend"]
        try:
            return order.index(current) >= order.index(required)
        except ValueError:
            return False
    
    async def _is_in_cooldown(
        self,
        user_id: str,
        rule: TriggerRule,
        current_time: datetime
    ) -> bool:
        """检查是否在冷却期"""
        if not self.db:
            return False
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT sent_at FROM proactive_messages
                    WHERE user_id = :user_id 
                      AND trigger_type = :trigger_type
                      AND status = 'sent'
                    ORDER BY sent_at DESC
                    LIMIT 1
                """),
                {
                    "user_id": user_id,
                    "trigger_type": rule.trigger_type.value
                }
            )
            row = result.fetchone()
            
            if row:
                last_sent = row[0]
                cooldown_end = last_sent + timedelta(hours=rule.cooldown_hours)
                return current_time < cooldown_end
            
            return False
        except Exception as e:
            logger.error(f"Failed to check cooldown: {e}")
            return True  # 出错时保守处理
    
    def _is_quiet_hours(self, current: time, pref: UserPreference) -> bool:
        """检查是否在免打扰时间"""
        start = pref.quiet_hours_start
        end = pref.quiet_hours_end
        
        if start <= end:
            return start <= current <= end
        else:
            # 跨午夜的情况
            return current >= start or current <= end
    
    async def _exceeded_daily_limit(
        self,
        user_id: str,
        pref: UserPreference
    ) -> bool:
        """检查是否超过每日限额"""
        if not self.db:
            return False
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT COUNT(*) FROM proactive_messages
                    WHERE user_id = :user_id 
                      AND DATE(sent_at) = CURRENT_DATE
                      AND status = 'sent'
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            count = row[0] if row else 0
            
            return count >= pref.max_daily_messages
        except Exception as e:
            logger.error(f"Failed to check daily limit: {e}")
            return True
    
    async def _check_condition(
        self,
        user_id: str,
        rule: TriggerRule,
        current_time: datetime
    ) -> bool:
        """检查具体触发条件"""
        if rule.trigger_type == TriggerType.TIME:
            return self._check_time_condition(rule.condition, current_time)
        
        elif rule.trigger_type == TriggerType.SILENCE:
            return await self._check_silence_condition(user_id, rule.condition)
        
        elif rule.trigger_type == TriggerType.EVENT:
            return await self._check_event_condition(user_id, rule.condition, current_time)
        
        elif rule.trigger_type == TriggerType.DECAY:
            return await self._check_decay_condition(user_id, rule.condition)
        
        return False
    
    def _check_time_condition(self, condition: Dict, current: datetime) -> bool:
        """检查时间条件"""
        target_time = condition.get("time", "08:00")
        hour, minute = map(int, target_time.split(":"))
        
        # 允许30分钟的窗口
        target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        window = timedelta(minutes=30)
        
        return target <= current <= target + window
    
    async def _check_silence_condition(self, user_id: str, condition: Dict) -> bool:
        """检查沉默条件"""
        if not self.db:
            return False
        
        days_threshold = condition.get("days", 3)
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT created_at FROM affinity_history
                    WHERE user_id = :user_id 
                      AND trigger_event = 'conversation'
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            
            if not row:
                return False
            
            last_interaction = row[0]
            days_since = (datetime.utcnow() - last_interaction).days
            
            return days_since >= days_threshold
        except Exception as e:
            logger.error(f"Failed to check silence condition: {e}")
            return False
    
    async def _check_event_condition(
        self,
        user_id: str,
        condition: Dict,
        current: datetime
    ) -> bool:
        """检查事件条件（如生日）"""
        event_type = condition.get("event")
        
        if event_type == "birthday":
            # TODO: 从用户资料或记忆中获取生日
            # 这里需要查询 Neo4j 中的生日记忆
            pass
        
        return False
    
    async def _check_decay_condition(self, user_id: str, condition: Dict) -> bool:
        """检查衰减条件"""
        # TODO: 查询 Neo4j 中即将衰减的重要关系
        return False


# ==================== 消息生成器 ====================

class MessageGenerator:
    """
    消息生成器 - 生成自然的主动消息
    
    核心原则：
    - 不能有情感勒索（"我等你好久了"）
    - 不能施压（"你怎么不理我"）
    - 要自然、温暖、不越界
    """
    
    # 消息模板（按好感度和触发类型分类）
    TEMPLATES = {
        "morning_greeting": {
            "acquaintance": [
                "早上好呀~新的一天开始了",
                "早安，今天也要加油哦",
            ],
            "friend": [
                "早安！今天有什么计划吗？",
                "早上好~昨晚睡得怎么样？",
                "新的一天，新的开始！早安~",
            ],
            "close_friend": [
                "早安宝！今天也要元气满满哦~",
                "起床啦~今天想做点什么？",
            ]
        },
        "evening_greeting": {
            "friend": [
                "晚上好~今天过得怎么样？",
                "忙了一天，辛苦啦~",
            ],
            "close_friend": [
                "晚安~今天有什么想分享的吗？",
                "一天结束了，好好休息哦~",
            ]
        },
        "gentle_checkin": {
            # 3天未互动 - 温和询问
            "acquaintance": [
                "好几天没聊了，最近忙吗？",
                "嗨~最近怎么样？",
            ],
            "friend": [
                "好久没聊天了，最近过得怎么样？",
                "想起你了，最近忙什么呢？",
            ],
            "close_friend": [
                "好几天没见你了，一切都好吗？",
                "最近怎么样呀？有空来聊聊~",
            ]
        },
        "care_message": {
            # 7天未互动 - 关怀消息
            "friend": [
                "好久不见！最近过得怎么样？",
                "有段时间没聊了，想问问你最近好不好",
            ],
            "close_friend": [
                "好久没聊天了，有点想你~一切都好吗？",
                "最近怎么样呀？有什么新鲜事吗？",
            ]
        },
        "birthday_wish": {
            "acquaintance": [
                "生日快乐！祝你新的一岁一切顺利~",
            ],
            "friend": [
                "生日快乐！🎂 希望你今天开开心心的！",
                "今天是你的生日！祝你心想事成~",
            ],
            "close_friend": [
                "生日快乐宝！🎉 新的一岁要更幸福哦！",
                "今天是你的大日子！祝你生日快乐，永远开心！",
            ]
        },
        "memory_recall": {
            # 记忆回调
            "friend": [
                "对了，上次你说{memory}，后来怎么样了？",
                "突然想起你之前提到{memory}，现在呢？",
            ],
            "close_friend": [
                "诶，想起来你说过{memory}，后来怎么样啦？",
                "对了对了，{memory}那件事后来怎么样了？",
            ]
        }
    }
    
    # 禁止的文案模式
    FORBIDDEN_PATTERNS = [
        "我等你",
        "你怎么不",
        "你是不是不要我",
        "我以为你",
        "甚是想念",
        "好想你",  # 过于亲密
        "离不开你",
        "只有你",
    ]
    
    def __init__(self):
        pass
    
    def generate(
        self,
        action: str,
        affinity_state: str,
        context: Dict[str, Any] = None
    ) -> Optional[str]:
        """
        生成主动消息
        
        Args:
            action: 动作类型（如 morning_greeting）
            affinity_state: 好感度状态
            context: 上下文（如记忆内容）
        """
        import random
        
        templates = self.TEMPLATES.get(action, {})
        state_templates = templates.get(affinity_state)
        
        # 如果当前状态没有模板，尝试降级
        if not state_templates:
            fallback_order = ["friend", "acquaintance"]
            for fallback in fallback_order:
                if fallback in templates:
                    state_templates = templates[fallback]
                    break
        
        if not state_templates:
            logger.warning(f"No template found for action={action}, state={affinity_state}")
            return None
        
        # 随机选择模板
        template = random.choice(state_templates)
        
        # 填充上下文变量
        if context:
            try:
                template = template.format(**context)
            except KeyError as e:
                logger.warning(f"Missing context key: {e}")
        
        # 安全检查
        if self._contains_forbidden_pattern(template):
            logger.error(f"Generated message contains forbidden pattern: {template}")
            return None
        
        return template
    
    def _contains_forbidden_pattern(self, text: str) -> bool:
        """检查是否包含禁止的文案模式"""
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern in text:
                return True
        return False
    
    def generate_with_memory(
        self,
        memory_content: str,
        affinity_state: str
    ) -> Optional[str]:
        """生成带记忆回调的消息"""
        return self.generate(
            action="memory_recall",
            affinity_state=affinity_state,
            context={"memory": memory_content}
        )


# ==================== 推送管理 ====================

class DeliveryManager:
    """
    推送管理 - 控制消息发送
    
    功能：
    1. 频率控制
    2. 推送渠道管理
    3. 发送状态追踪
    """
    
    def __init__(self, db_session: AsyncSession = None):
        self.db = db_session

    def _is_valid_transition(self, current: str, target: str) -> bool:
        allowed = {
            "pending": {"sent", "cancelled"},
            "sent": {"delivered", "read", "ignored", "cancelled"},
            "delivered": {"read", "ignored", "cancelled"},
            "read": {"read"},
            "ignored": {"ignored"},
            "cancelled": {"cancelled"},
        }
        return target in allowed.get(current, set())
    
    async def schedule_message(
        self,
        user_id: str,
        trigger_type: str,
        content: str,
        scheduled_at: datetime = None,
        metadata: Dict = None
    ) -> ProactiveMessage:
        """调度一条主动消息"""
        message = ProactiveMessage(
            id=str(uuid.uuid4()),
            user_id=user_id,
            trigger_type=trigger_type,
            trigger_rule_id=None,
            content=content,
            scheduled_at=scheduled_at or datetime.now(),
            status="pending",
            metadata=metadata or {}
        )
        
        if self.db:
            await self._save_message(message)
        
        return message
    
    async def send_message(self, message: ProactiveMessage) -> bool:
        """
        发送消息
        
        实际发送逻辑需要对接推送服务（如 Firebase、APNs）
        """
        try:
            # TODO: 对接实际的推送服务
            # await push_service.send(message.user_id, message.content)
            
            current_status = message.status or "pending"
            if not self._is_valid_transition(current_status, "sent"):
                return False

            message.sent_at = datetime.utcnow()
            message.status = "sent"
            
            if self.db:
                await self._update_message_status(message)
            
            logger.info(f"Sent proactive message to {message.user_id}: {message.content[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def mark_as_read(self, message_id: str) -> bool:
        """标记消息已读"""
        if not self.db:
            return True
        
        try:
            await self.db.execute(
                text("""
                    UPDATE proactive_messages
                    SET read_at = NOW(), status = 'read', user_response = 'replied'
                    WHERE id = :id
                      AND status IN ('sent', 'delivered')
                """),
                {"id": message_id}
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to mark as read: {e}")
            return False
    
    async def record_user_response(
        self,
        message_id: str,
        response: UserResponse
    ) -> bool:
        """记录用户响应"""
        if not self.db:
            return True
        
        try:
            await self.db.execute(
                text("""
                    UPDATE proactive_messages
                    SET user_response = :response
                    WHERE id = :id
                """),
                {"id": message_id, "response": response.value}
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to record response: {e}")
            return False
    
    async def _save_message(self, message: ProactiveMessage) -> bool:
        """保存消息到数据库"""
        try:
            await self.db.execute(
                text("""
                    INSERT INTO proactive_messages
                    (id, user_id, trigger_type, content, scheduled_at, status, metadata)
                    VALUES (:id, :user_id, :trigger_type, :content, :scheduled_at, :status, :metadata)
                """),
                {
                    "id": message.id,
                    "user_id": message.user_id,
                    "trigger_type": message.trigger_type,
                    "content": message.content,
                    "scheduled_at": message.scheduled_at,
                    "status": message.status,
                    "metadata": json.dumps(message.metadata)
                }
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            return False
    
    async def _update_message_status(self, message: ProactiveMessage) -> bool:
        """更新消息状态"""
        try:
            await self.db.execute(
                text("""
                    UPDATE proactive_messages
                    SET sent_at = :sent_at, status = :status
                    WHERE id = :id AND status = 'pending'
                """),
                {
                    "id": message.id,
                    "sent_at": message.sent_at,
                    "status": message.status
                }
            )
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update message status: {e}")
            return False


# ==================== 反馈追踪 ====================

class FeedbackTracker:
    """
    反馈追踪 - 学习用户对主动消息的偏好
    
    功能：
    1. 追踪用户响应率
    2. 学习最佳发送时间
    3. 调整触发策略
    """
    
    def __init__(self, db_session: AsyncSession = None):
        self.db = db_session
    
    async def get_response_rate(self, user_id: str, days: int = 30) -> float:
        """获取用户响应率"""
        if not self.db:
            return 0.5
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT 
                        COUNT(*) FILTER (WHERE user_response = 'replied') as replied,
                        COUNT(*) as total
                    FROM proactive_messages
                    WHERE user_id = :user_id 
                      AND sent_at > NOW() - INTERVAL :days DAY
                      AND sent_at IS NOT NULL
                """),
                {"user_id": user_id, "days": f"{days} days"}
            )
            row = result.fetchone()
            
            if row and row[1] > 0:
                return row[0] / row[1]
            return 0.5
        except Exception as e:
            logger.error(f"Failed to get response rate: {e}")
            return 0.5
    
    async def get_best_send_time(self, user_id: str) -> Optional[time]:
        """获取用户最佳发送时间（基于历史响应）"""
        if not self.db:
            return None
        
        try:
            result = await self.db.execute(
                text("""
                    SELECT EXTRACT(HOUR FROM sent_at) as hour, COUNT(*) as count
                    FROM proactive_messages
                    WHERE user_id = :user_id 
                      AND user_response = 'replied'
                      AND sent_at IS NOT NULL
                    GROUP BY hour
                    ORDER BY count DESC
                    LIMIT 1
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()
            
            if row:
                return time(hour=int(row[0]))
            return None
        except Exception as e:
            logger.error(f"Failed to get best send time: {e}")
            return None
    
    async def should_reduce_frequency(self, user_id: str) -> bool:
        """判断是否应该降低发送频率"""
        response_rate = await self.get_response_rate(user_id)
        
        # 如果响应率低于 20%，建议降低频率
        return response_rate < 0.2


# ==================== 主服务 ====================

class ProactiveService:
    """
    主动对话服务 - 整合所有模块
    """
    
    def __init__(self, db_session: AsyncSession = None):
        self.db = db_session
        self.trigger_engine = TriggerEngine(db_session)
        self.message_generator = MessageGenerator()
        self.delivery_manager = DeliveryManager(db_session)
        self.feedback_tracker = FeedbackTracker(db_session)
    
    async def process_user(
        self,
        user_id: str,
        affinity_state: str,
        user_preference: UserPreference = None
    ) -> Optional[ProactiveMessage]:
        """
        处理单个用户的主动消息
        
        由 Celery Beat 定时调用
        """
        if user_preference is None:
            user_preference = UserPreference(user_id=user_id)

        if self.db:
            rules_config = await self._load_user_rules_config(user_id)
            self.trigger_engine.load_rules_from_config(rules_config)
        
        # 1. 检查触发条件
        triggered_rules = await self.trigger_engine.check_triggers(
            user_id, affinity_state, user_preference
        )
        
        if not triggered_rules:
            return None
        
        # 2. 选择最高优先级的规则
        rule = triggered_rules[0]
        
        # 3. 检查是否应该降低频率
        if await self.feedback_tracker.should_reduce_frequency(user_id):
            logger.info(f"Skipping proactive message for {user_id} due to low response rate")
            return None
        
        # 4. 生成消息
        content = self.message_generator.generate(
            action=rule.action,
            affinity_state=affinity_state
        )
        
        if not content:
            return None
        
        # 5. 调度并发送
        message = await self.delivery_manager.schedule_message(
            user_id=user_id,
            trigger_type=rule.trigger_type.value,
            content=content
        )
        
        await self.delivery_manager.send_message(message)
        
        return message
    
    async def get_user_preference(self, user_id: str) -> UserPreference:
        """获取用户偏好设置"""
        if not self.db:
            return UserPreference(user_id=user_id)

        try:
            import uuid as _uuid
            from sqlalchemy import select
            from app.models.outbox import UserProactivePreference

            user_uuid = _uuid.UUID(user_id)
            result = await self.db.execute(
                select(UserProactivePreference).where(UserProactivePreference.user_id == user_uuid)
            )
            row = result.scalar_one_or_none()
            if not row:
                return UserPreference(user_id=user_id)

            return UserPreference(
                user_id=user_id,
                proactive_enabled=bool(row.proactive_enabled),
                morning_greeting=bool(row.morning_greeting),
                evening_greeting=bool(row.evening_greeting),
                silence_reminder=bool(row.silence_reminder),
                event_reminder=bool(row.event_reminder),
                quiet_hours_start=row.quiet_hours_start or time(22, 0),
                quiet_hours_end=row.quiet_hours_end or time(8, 0),
                max_daily_messages=row.max_daily_messages or 2,
                preferred_greeting_time=row.preferred_greeting_time,
                timezone=row.timezone or "Asia/Shanghai",
            )
        except Exception as e:
            logger.error(f"Failed to load user preference: {e}")
            return UserPreference(user_id=user_id)
    
    async def update_user_preference(
        self,
        user_id: str,
        updates: Dict[str, Any]
    ) -> UserPreference:
        """更新用户偏好设置"""
        pref = await self.get_user_preference(user_id)

        for key, value in updates.items():
            if hasattr(pref, key):
                setattr(pref, key, value)

        if not self.db:
            return pref

        try:
            import uuid as _uuid
            from sqlalchemy import select
            from app.models.outbox import UserProactivePreference

            user_uuid = _uuid.UUID(user_id)
            result = await self.db.execute(
                select(UserProactivePreference).where(UserProactivePreference.user_id == user_uuid)
            )
            row = result.scalar_one_or_none()
            if not row:
                row = UserProactivePreference(user_id=user_uuid)
                self.db.add(row)

            row.proactive_enabled = pref.proactive_enabled
            row.morning_greeting = pref.morning_greeting
            row.evening_greeting = pref.evening_greeting
            row.silence_reminder = pref.silence_reminder
            row.event_reminder = pref.event_reminder
            row.quiet_hours_start = pref.quiet_hours_start
            row.quiet_hours_end = pref.quiet_hours_end
            row.max_daily_messages = pref.max_daily_messages
            row.preferred_greeting_time = pref.preferred_greeting_time
            row.timezone = pref.timezone

            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to update user preference: {e}")

        return pref

    async def _load_user_rules_config(self, user_id: str) -> Any:
        try:
            import uuid as _uuid
            from sqlalchemy import select
            from app.models.user import User

            user_uuid = _uuid.UUID(user_id)
            result = await self.db.execute(select(User).where(User.id == user_uuid))
            user = result.scalar_one_or_none()
            if not user:
                return None
            settings_obj = user.settings or {}
            return settings_obj.get("proactive_rules")
        except Exception:
            return None


def _build_trigger_rules_from_dicts(config: Any) -> List[TriggerRule]:
    if not isinstance(config, list):
        return []
    rules: List[TriggerRule] = []
    for item in config:
        if not isinstance(item, dict):
            continue
        trigger_type = item.get("trigger_type")
        condition = item.get("condition")
        action = item.get("action")
        if not trigger_type or not condition or not action:
            continue
        try:
            tt = TriggerType(trigger_type)
        except Exception:
            continue
        rules.append(
            TriggerRule(
                trigger_type=tt,
                condition=condition,
                action=action,
                priority=int(item.get("priority", 5)),
                cooldown_hours=int(item.get("cooldown_hours", 24)),
                min_affinity_state=str(item.get("min_affinity_state", "acquaintance")),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return rules
