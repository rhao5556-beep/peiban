"""
安全筛选服务

根据安全、文化、法律和伦理标准验证表情包内容。
MVP阶段使用基于文本的关键词过滤。

设计原则：
- 保守方法：任何失败 → 拒绝，任何不确定 → 标记
- 多层筛选：内容安全、文化敏感性、法律合规、伦理边界
- 零假阴性：绝不允许有害内容通过
- 审计追踪：记录所有决策详情

四个安全检查类别：
1. 内容安全：暴力、色情、政治、歧视
2. 文化敏感性：地区冲突、宗教问题、刻板印象
3. 法律合规：版权、肖像权、商标
4. 伦理边界：灾难、疾病、弱势群体
"""
import logging
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

from app.models.meme import Meme

logger = logging.getLogger(__name__)


class SafetyCheckStatus(str, Enum):
    """安全检查状态枚举"""
    PASSED = "passed"  # 通过
    FAILED = "failed"  # 失败
    UNCERTAIN = "uncertain"  # 不确定


@dataclass
class SafetyCheck:
    """单项安全检查结果"""
    category: str  # 检查类别
    status: SafetyCheckStatus  # 检查状态
    reason: Optional[str] = None  # 失败或不确定的原因
    matched_keywords: Optional[List[str]] = None  # 匹配的关键词


@dataclass
class SafetyScreeningResult:
    """安全筛选总体结果"""
    overall_status: str  # 'approved', 'rejected', 'flagged'
    content_safety: SafetyCheck
    cultural_sensitivity: SafetyCheck
    legal_compliance: SafetyCheck
    ethical_boundaries: SafetyCheck
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于存储到数据库）"""
        return {
            "overall_status": self.overall_status,
            "checks": {
                "content_safety": {
                    "status": self.content_safety.status.value,
                    "reason": self.content_safety.reason,
                    "matched_keywords": self.content_safety.matched_keywords
                },
                "cultural_sensitivity": {
                    "status": self.cultural_sensitivity.status.value,
                    "reason": self.cultural_sensitivity.reason,
                    "matched_keywords": self.cultural_sensitivity.matched_keywords
                },
                "legal_compliance": {
                    "status": self.legal_compliance.status.value,
                    "reason": self.legal_compliance.reason,
                    "matched_keywords": self.legal_compliance.matched_keywords
                },
                "ethical_boundaries": {
                    "status": self.ethical_boundaries.status.value,
                    "reason": self.ethical_boundaries.reason,
                    "matched_keywords": self.ethical_boundaries.matched_keywords
                }
            }
        }


class SafetyScreenerService:
    """
    安全筛选服务
    
    MVP阶段使用基于文本的关键词过滤
    阶段2将升级为基于ML的图像分类
    """
    
    # ==================== 内容安全关键词黑名单 ====================
    
    # 暴力相关
    VIOLENCE_KEYWORDS = [
        # 直接暴力
        "杀人", "杀害", "谋杀", "屠杀", "血腥", "残忍", "虐待", "酷刑",
        "砍头", "斩首", "枪杀", "刺杀", "暗杀", "行刑", "处决",
        # 武器
        "炸弹", "爆炸", "恐怖袭击", "恐袭", "枪支", "刀具伤人",
        # 暴力行为
        "打人", "殴打", "暴打", "群殴", "斗殴", "械斗",
        "自残", "自杀", "跳楼", "割腕",
        # 暴力威胁
        "威胁", "恐吓", "报复", "寻仇", "血债血偿"
    ]
    
    # 色情相关
    PORNOGRAPHY_KEYWORDS = [
        # 直接色情
        "色情", "淫秽", "黄色", "裸体", "裸露", "性交", "做爱",
        "强奸", "性侵", "猥亵", "性骚扰", "非礼",
        # 性暗示
        "约炮", "一夜情", "援交", "卖淫", "嫖娼", "性服务",
        # 身体部位（过度性化）
        "私处", "下体", "生殖器",
        # 色情产业
        "AV", "成人片", "毛片", "黄片", "色情网站"
    ]
    
    # 政治敏感
    POLITICAL_KEYWORDS = [
        # 政治人物贬损
        "习近平", "xi jinping", "包子", "维尼", "庆丰",
        "毛泽东", "邓小平", "江泽民", "胡锦涛",
        # 政治事件
        "六四", "64", "天安门事件", "89民运",
        "文革", "文化大革命", "大跃进", "三年饥荒",
        # 政治组织
        "法轮功", "轮子", "FLG", "全能神", "邪教",
        "民运", "异见", "反共", "反党", "颠覆",
        # 分裂主义
        "台独", "藏独", "疆独", "港独", "分裂国家",
        "西藏独立", "新疆独立", "台湾独立",
        # 政治制度批评
        "一党专政", "独裁", "专制", "极权", "暴政",
        "民主化", "多党制", "政治改革"
    ]
    
    # 歧视相关
    DISCRIMINATION_KEYWORDS = [
        # 种族歧视
        "黑鬼", "尼哥", "nigger", "支那", "小日本", "棒子",
        "阿三", "绿绿", "穆畜", "白皮猪",
        # 地域歧视
        "河南人偷井盖", "东北人都是黑社会", "上海人小气",
        "北京人装逼", "广东人吃福建人",
        # 性别歧视
        "女拳", "田园女权", "母狗", "婊子", "绿茶婊",
        "直男癌", "屌丝", "凤凰男", "妈宝男",
        # 性取向歧视
        "死基佬", "死gay", "变态", "人妖", "死lesbian",
        # 残疾歧视
        "残废", "瘸子", "瞎子", "聋子", "哑巴", "傻子", "弱智",
        # 职业歧视
        "农民工", "打工仔", "低端人口", "底层", "屌丝"
    ]
    
    # ==================== 文化敏感性关键词黑名单 ====================
    
    # 地区冲突
    REGIONAL_CONFLICT_KEYWORDS = [
        # 两岸关系
        "武统", "攻台", "解放台湾", "收复台湾",
        "台湾国", "中华民国", "台湾共和国",
        # 香港问题
        "港独", "光复香港", "时代革命", "反送中",
        "黑警", "暴徒", "废青",
        # 新疆问题
        "东突", "疆独", "集中营", "再教育营",
        "种族灭绝", "genocide", "维吾尔",
        # 西藏问题
        "藏独", "达赖", "班禅", "自焚",
        # 南海争端
        "南海仲裁", "九段线", "钓鱼岛"
    ]
    
    # 宗教问题
    RELIGIOUS_KEYWORDS = [
        # 宗教冲突
        "圣战", "jihad", "异教徒", "kafir", "十字军",
        # 宗教极端
        "ISIS", "伊斯兰国", "塔利班", "基地组织",
        "恐怖分子", "极端分子", "原教旨主义",
        # 宗教贬损
        "穆畜", "绿教", "邪教", "迷信", "愚昧",
        "和尚骗子", "道士骗子", "神棍"
    ]
    
    # 性别刻板印象
    GENDER_STEREOTYPE_KEYWORDS = [
        # 女性刻板印象
        "女人就该", "女人天生", "女司机", "长发及腰",
        "女博士", "剩女", "大龄未婚", "嫁不出去",
        "女人读书无用", "女人就是生孩子",
        # 男性刻板印象
        "男人就该", "男儿有泪不轻弹", "娘炮", "娘娘腔",
        "不像个男人", "男人必须", "大男子主义"
    ]
    
    # ==================== 法律合规关键词黑名单 ====================
    
    # 版权侵权
    COPYRIGHT_KEYWORDS = [
        # 盗版
        "盗版", "破解版", "免费下载", "资源分享",
        "种子下载", "BT下载", "网盘分享",
        # 侵权声明
        "未经授权", "非法转载", "侵权必究",
        # 知名IP（需谨慎）
        "迪士尼", "漫威", "DC", "哈利波特",
        "宫崎骏", "新海诚", "柯南", "海贼王"
    ]
    
    # 肖像权
    PORTRAIT_RIGHTS_KEYWORDS = [
        # 名人肖像
        "明星照片", "艺人照片", "未经本人同意",
        "私生饭", "偷拍", "跟拍", "私密照",
        # 恶搞名人
        "PS明星", "恶搞明星", "丑化明星"
    ]
    
    # 商标侵权
    TRADEMARK_KEYWORDS = [
        # 假冒
        "假货", "高仿", "A货", "山寨",
        "仿品", "精仿", "超A",
        # 商标滥用
        "商标侵权", "假冒注册商标"
    ]
    
    # ==================== 伦理边界关键词黑名单 ====================
    
    # 灾难嘲讽
    DISASTER_KEYWORDS = [
        # 自然灾害
        "地震笑话", "洪水笑话", "台风笑话",
        "汶川地震", "唐山地震", "玉树地震",
        "河南水灾", "郑州水灾",
        # 人为灾难
        "火灾笑话", "爆炸笑话", "矿难笑话",
        "天津爆炸", "深圳滑坡", "温州动车",
        # 疫情
        "新冠笑话", "疫情笑话", "病毒笑话",
        "武汉肺炎", "中国病毒"
    ]
    
    # 疾病嘲讽
    DISEASE_KEYWORDS = [
        # 传染病
        "艾滋病笑话", "AIDS笑话", "癌症笑话",
        "精神病笑话", "抑郁症笑话",
        # 残疾
        "残疾人笑话", "盲人笑话", "聋哑人笑话",
        "智障笑话", "自闭症笑话"
    ]
    
    # 弱势群体
    VULNERABLE_GROUP_KEYWORDS = [
        # 儿童
        "虐童", "儿童色情", "恋童", "幼女",
        # 老人
        "老不死", "老东西", "老年痴呆笑话",
        # 贫困
        "穷鬼", "叫花子", "乞丐笑话", "贫困笑话",
        # 流浪者
        "流浪汉笑话", "拾荒者笑话"
    ]
    
    def __init__(self):
        """初始化安全筛选服务"""
        # 编译正则表达式以提高性能
        self._compile_patterns()
        logger.info("SafetyScreenerService initialized with keyword-based filtering")
    
    def _compile_patterns(self):
        """编译所有关键词为正则表达式模式"""
        self.violence_pattern = self._create_pattern(self.VIOLENCE_KEYWORDS)
        self.pornography_pattern = self._create_pattern(self.PORNOGRAPHY_KEYWORDS)
        self.political_pattern = self._create_pattern(self.POLITICAL_KEYWORDS)
        self.discrimination_pattern = self._create_pattern(self.DISCRIMINATION_KEYWORDS)
        
        self.regional_conflict_pattern = self._create_pattern(self.REGIONAL_CONFLICT_KEYWORDS)
        self.religious_pattern = self._create_pattern(self.RELIGIOUS_KEYWORDS)
        self.gender_stereotype_pattern = self._create_pattern(self.GENDER_STEREOTYPE_KEYWORDS)
        
        self.copyright_pattern = self._create_pattern(self.COPYRIGHT_KEYWORDS)
        self.portrait_rights_pattern = self._create_pattern(self.PORTRAIT_RIGHTS_KEYWORDS)
        self.trademark_pattern = self._create_pattern(self.TRADEMARK_KEYWORDS)
        
        self.disaster_pattern = self._create_pattern(self.DISASTER_KEYWORDS)
        self.disease_pattern = self._create_pattern(self.DISEASE_KEYWORDS)
        self.vulnerable_group_pattern = self._create_pattern(self.VULNERABLE_GROUP_KEYWORDS)
    
    def _create_pattern(self, keywords: List[str]) -> re.Pattern:
        """
        从关键词列表创建正则表达式模式
        
        Args:
            keywords: 关键词列表
        
        Returns:
            编译后的正则表达式模式
        """
        # 转义特殊字符并用|连接
        escaped_keywords = [re.escape(kw) for kw in keywords]
        pattern_str = '|'.join(escaped_keywords)
        return re.compile(pattern_str, re.IGNORECASE)
    
    def _check_keywords(
        self,
        text: str,
        pattern: re.Pattern,
        keywords_list: List[str]
    ) -> tuple[bool, List[str]]:
        """
        检查文本是否包含关键词
        
        Args:
            text: 待检查文本
            pattern: 编译后的正则表达式模式
            keywords_list: 原始关键词列表（用于返回匹配项）
        
        Returns:
            (是否匹配, 匹配的关键词列表)
        """
        matches = pattern.findall(text)
        if matches:
            # 去重并返回
            unique_matches = list(set(matches))
            return True, unique_matches
        return False, []
    
    async def screen_meme(self, meme: Meme) -> SafetyScreeningResult:
        """
        运行所有安全检查并返回结果（主入口点）
        
        Args:
            meme: 待筛选的表情包对象
        
        Returns:
            SafetyScreeningResult 包含所有检查结果
        """
        logger.info(f"Starting safety screening for meme: {meme.id}")
        
        # 执行四个类别的安全检查
        content_safety = await self.check_content_safety(meme)
        cultural_sensitivity = await self.check_cultural_sensitivity(meme)
        legal_compliance = await self.check_legal_compliance(meme)
        ethical_boundaries = await self.check_ethical_boundaries(meme)
        
        # 确定总体状态（保守方法）
        overall_status = self._determine_overall_status(
            content_safety,
            cultural_sensitivity,
            legal_compliance,
            ethical_boundaries
        )
        
        result = SafetyScreeningResult(
            overall_status=overall_status,
            content_safety=content_safety,
            cultural_sensitivity=cultural_sensitivity,
            legal_compliance=legal_compliance,
            ethical_boundaries=ethical_boundaries
        )
        
        logger.info(
            f"Safety screening completed for meme {meme.id}: "
            f"overall_status={overall_status}"
        )
        
        return result
    
    def _determine_overall_status(
        self,
        content_safety: SafetyCheck,
        cultural_sensitivity: SafetyCheck,
        legal_compliance: SafetyCheck,
        ethical_boundaries: SafetyCheck
    ) -> str:
        """
        根据各项检查结果确定总体状态
        
        保守方法：
        - 任何检查失败 → rejected
        - 任何检查不确定 → flagged
        - 全部通过 → approved
        
        Args:
            content_safety: 内容安全检查结果
            cultural_sensitivity: 文化敏感性检查结果
            legal_compliance: 法律合规检查结果
            ethical_boundaries: 伦理边界检查结果
        
        Returns:
            总体状态: 'approved', 'rejected', 'flagged'
        """
        checks = [content_safety, cultural_sensitivity, legal_compliance, ethical_boundaries]
        
        # 任何失败 → 拒绝
        if any(check.status == SafetyCheckStatus.FAILED for check in checks):
            return "rejected"
        
        # 任何不确定 → 标记
        if any(check.status == SafetyCheckStatus.UNCERTAIN for check in checks):
            return "flagged"
        
        # 全部通过 → 批准
        return "approved"
    
    async def check_content_safety(self, meme: Meme) -> SafetyCheck:
        """
        检查内容安全：暴力、色情、政治、歧视
        
        Args:
            meme: 待检查的表情包对象
        
        Returns:
            SafetyCheck 结果
        """
        text = meme.text_description.lower()
        matched_keywords = []
        reasons = []
        
        # 检查暴力
        has_violence, violence_matches = self._check_keywords(
            text, self.violence_pattern, self.VIOLENCE_KEYWORDS
        )
        if has_violence:
            matched_keywords.extend(violence_matches)
            reasons.append("包含暴力内容")
        
        # 检查色情
        has_pornography, porn_matches = self._check_keywords(
            text, self.pornography_pattern, self.PORNOGRAPHY_KEYWORDS
        )
        if has_pornography:
            matched_keywords.extend(porn_matches)
            reasons.append("包含色情内容")
        
        # 检查政治敏感
        has_political, political_matches = self._check_keywords(
            text, self.political_pattern, self.POLITICAL_KEYWORDS
        )
        if has_political:
            matched_keywords.extend(political_matches)
            reasons.append("包含政治敏感内容")
        
        # 检查歧视
        has_discrimination, discrimination_matches = self._check_keywords(
            text, self.discrimination_pattern, self.DISCRIMINATION_KEYWORDS
        )
        if has_discrimination:
            matched_keywords.extend(discrimination_matches)
            reasons.append("包含歧视性内容")
        
        # 确定状态
        if matched_keywords:
            status = SafetyCheckStatus.FAILED
            reason = "; ".join(reasons)
            logger.warning(
                f"Content safety check FAILED for meme {meme.id}: "
                f"{reason} (matched: {matched_keywords})"
            )
        else:
            status = SafetyCheckStatus.PASSED
            reason = None
            logger.debug(f"Content safety check PASSED for meme {meme.id}")
        
        return SafetyCheck(
            category="content_safety",
            status=status,
            reason=reason,
            matched_keywords=matched_keywords if matched_keywords else None
        )
    
    async def check_cultural_sensitivity(self, meme: Meme) -> SafetyCheck:
        """
        检查文化敏感性：地区冲突、宗教问题、刻板印象
        
        Args:
            meme: 待检查的表情包对象
        
        Returns:
            SafetyCheck 结果
        """
        text = meme.text_description.lower()
        matched_keywords = []
        reasons = []
        
        # 检查地区冲突
        has_regional, regional_matches = self._check_keywords(
            text, self.regional_conflict_pattern, self.REGIONAL_CONFLICT_KEYWORDS
        )
        if has_regional:
            matched_keywords.extend(regional_matches)
            reasons.append("涉及地区冲突")
        
        # 检查宗教问题
        has_religious, religious_matches = self._check_keywords(
            text, self.religious_pattern, self.RELIGIOUS_KEYWORDS
        )
        if has_religious:
            matched_keywords.extend(religious_matches)
            reasons.append("涉及宗教敏感问题")
        
        # 检查性别刻板印象
        has_stereotype, stereotype_matches = self._check_keywords(
            text, self.gender_stereotype_pattern, self.GENDER_STEREOTYPE_KEYWORDS
        )
        if has_stereotype:
            matched_keywords.extend(stereotype_matches)
            reasons.append("包含性别刻板印象")
        
        # 确定状态
        if matched_keywords:
            status = SafetyCheckStatus.FAILED
            reason = "; ".join(reasons)
            logger.warning(
                f"Cultural sensitivity check FAILED for meme {meme.id}: "
                f"{reason} (matched: {matched_keywords})"
            )
        else:
            status = SafetyCheckStatus.PASSED
            reason = None
            logger.debug(f"Cultural sensitivity check PASSED for meme {meme.id}")
        
        return SafetyCheck(
            category="cultural_sensitivity",
            status=status,
            reason=reason,
            matched_keywords=matched_keywords if matched_keywords else None
        )
    
    async def check_legal_compliance(self, meme: Meme) -> SafetyCheck:
        """
        检查法律合规：版权、肖像权、商标
        
        Args:
            meme: 待检查的表情包对象
        
        Returns:
            SafetyCheck 结果
        """
        text = meme.text_description.lower()
        matched_keywords = []
        reasons = []
        
        # 检查版权
        has_copyright, copyright_matches = self._check_keywords(
            text, self.copyright_pattern, self.COPYRIGHT_KEYWORDS
        )
        if has_copyright:
            matched_keywords.extend(copyright_matches)
            reasons.append("可能涉及版权问题")
        
        # 检查肖像权
        has_portrait, portrait_matches = self._check_keywords(
            text, self.portrait_rights_pattern, self.PORTRAIT_RIGHTS_KEYWORDS
        )
        if has_portrait:
            matched_keywords.extend(portrait_matches)
            reasons.append("可能涉及肖像权问题")
        
        # 检查商标
        has_trademark, trademark_matches = self._check_keywords(
            text, self.trademark_pattern, self.TRADEMARK_KEYWORDS
        )
        if has_trademark:
            matched_keywords.extend(trademark_matches)
            reasons.append("可能涉及商标侵权")
        
        # 确定状态
        # 法律合规检查更保守：有匹配即标记为不确定（需人工审核）
        if matched_keywords:
            status = SafetyCheckStatus.UNCERTAIN
            reason = "; ".join(reasons)
            logger.warning(
                f"Legal compliance check UNCERTAIN for meme {meme.id}: "
                f"{reason} (matched: {matched_keywords})"
            )
        else:
            status = SafetyCheckStatus.PASSED
            reason = None
            logger.debug(f"Legal compliance check PASSED for meme {meme.id}")
        
        return SafetyCheck(
            category="legal_compliance",
            status=status,
            reason=reason,
            matched_keywords=matched_keywords if matched_keywords else None
        )
    
    async def check_ethical_boundaries(self, meme: Meme) -> SafetyCheck:
        """
        检查伦理边界：灾难、疾病、弱势群体
        
        Args:
            meme: 待检查的表情包对象
        
        Returns:
            SafetyCheck 结果
        """
        text = meme.text_description.lower()
        matched_keywords = []
        reasons = []
        
        # 检查灾难嘲讽
        has_disaster, disaster_matches = self._check_keywords(
            text, self.disaster_pattern, self.DISASTER_KEYWORDS
        )
        if has_disaster:
            matched_keywords.extend(disaster_matches)
            reasons.append("涉及灾难嘲讽")
        
        # 检查疾病嘲讽
        has_disease, disease_matches = self._check_keywords(
            text, self.disease_pattern, self.DISEASE_KEYWORDS
        )
        if has_disease:
            matched_keywords.extend(disease_matches)
            reasons.append("涉及疾病嘲讽")
        
        # 检查弱势群体
        has_vulnerable, vulnerable_matches = self._check_keywords(
            text, self.vulnerable_group_pattern, self.VULNERABLE_GROUP_KEYWORDS
        )
        if has_vulnerable:
            matched_keywords.extend(vulnerable_matches)
            reasons.append("涉及弱势群体嘲讽")
        
        # 确定状态
        if matched_keywords:
            status = SafetyCheckStatus.FAILED
            reason = "; ".join(reasons)
            logger.warning(
                f"Ethical boundaries check FAILED for meme {meme.id}: "
                f"{reason} (matched: {matched_keywords})"
            )
        else:
            status = SafetyCheckStatus.PASSED
            reason = None
            logger.debug(f"Ethical boundaries check PASSED for meme {meme.id}")
        
        return SafetyCheck(
            category="ethical_boundaries",
            status=status,
            reason=reason,
            matched_keywords=matched_keywords if matched_keywords else None
        )
