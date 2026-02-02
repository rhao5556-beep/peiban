import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AnswerPolicyType(str, Enum):
    STRICT_FACTUAL = "strict_factual"
    REASONING = "reasoning"


_REL_TIME_RE = re.compile(r"\b(yesterday|today|tomorrow|last\s+\w+|next\s+\w+)\b", flags=re.IGNORECASE)
_LEADING_PREFIX_RE = re.compile(
    r"^(根据对话记录[,，]?\s*|答案是[:：]?\s*|最终答案[:：]?\s*|According to the conversation[, ]*|The answer is[: ]*)",
    flags=re.IGNORECASE,
)

_MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def extract_question_text(message: str) -> str:
    s = message or ""
    idx = s.lower().rfind("question:")
    if idx >= 0:
        tail = s[idx + len("Question:") :]
        m = re.search(r"\n\s*answer\s*:", tail, flags=re.IGNORECASE)
        if m:
            tail = tail[: m.start()]
        return tail.strip()
    return s.strip()


def extract_context_time(text: str) -> Optional[str]:
    s = text or ""
    m = re.search(r"Session time:\s*(.+)", s, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip() or None


def _parse_day_month_year(text: str) -> Optional[tuple[int, int, int]]:
    s = (text or "").strip()
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s*,?\s*(\d{4})\b", s)
    if not m:
        return None
    day = int(m.group(1))
    month_name = m.group(2).strip().lower()
    year = int(m.group(3))
    month_map = {v.lower(): k for k, v in _MONTH_NAMES.items()}
    month = month_map.get(month_name)
    if not month:
        month3 = month_name[:3]
        for k, v in month_map.items():
            if k[:3] == month3:
                month = v
                break
    if not month:
        return None
    return year, month, day


def _parse_iso_date(text: str) -> Optional[tuple[int, int, int]]:
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _format_locomo_date(year: int, month: int, day: int) -> str:
    month_name = _MONTH_NAMES.get(int(month))
    if not month_name:
        return f"{year:04d}-{month:02d}-{day:02d}"
    return f"{int(day)} {month_name} {int(year)}"


def _is_temporal_question(question_text: str) -> bool:
    q = (question_text or "").lower()
    markers = [
        "when",
        "what time",
        "what date",
        "which day",
        "what year",
        "in which year",
        "year",
        "month",
        "date",
        "哪天",
        "什么时候",
        "何时",
        "哪年",
        "年份",
        "哪个月",
        "月份",
        "日期",
        "时间",
    ]
    return any(m in q for m in markers)


def _wants_year_only(question_text: str) -> bool:
    q = (question_text or "").lower()
    markers = ["what year", "in which year", "year", "年份", "哪年", "哪一年"]
    return any(m in q for m in markers)


def postprocess_temporal_answer(answer: str, session_time: Optional[str], question_text: str) -> str:
    s = (answer or "").strip()
    if not s:
        return s

    s = re.sub(r"\b\d{1,2}:\d{2}\s*(?:am|pm)\s+on\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b\d{1,2}:\d{2}\s*(?:am|pm)\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(", ", " ").replace(",", " ").strip()
    s = re.sub(r"\s+", " ", s).strip()

    wants_year = _wants_year_only(question_text)

    session_ymd = _parse_day_month_year(session_time or "")
    if session_ymd:
        sy, sm, sd = session_ymd
        session_dt = datetime(sy, sm, sd)
    else:
        session_dt = None

    s_lower = s.lower()
    if session_dt:
        if s_lower == "yesterday":
            d = session_dt - timedelta(days=1)
            return str(d.year) if wants_year else _format_locomo_date(d.year, d.month, d.day)
        if s_lower == "today":
            d = session_dt
            return str(d.year) if wants_year else _format_locomo_date(d.year, d.month, d.day)
        if s_lower == "tomorrow":
            d = session_dt + timedelta(days=1)
            return str(d.year) if wants_year else _format_locomo_date(d.year, d.month, d.day)
        if s_lower == "last year" or " last year" in s_lower:
            return str(session_dt.year - 1)

    if re.fullmatch(r"\d{4}", s):
        return s

    iso = _parse_iso_date(s)
    if iso:
        y, m, d = iso
        return str(y) if wants_year else _format_locomo_date(y, m, d)

    dmy = _parse_day_month_year(s)
    if dmy:
        y, m, d = dmy
        return str(y) if wants_year else _format_locomo_date(y, m, d)

    if wants_year:
        m = re.search(r"\b(\d{4})\b", s)
        if m:
            return m.group(1)

    return s


def build_extractive_suffix() -> str:
    return (
        "\n【抽取式回答要求 - 必须严格遵守】\n"
        "1) 仅从“权威证据”中复制原文片段作为答案，不要改写、不补充、不解释\n"
        "2) 若证据中找不到直接支持的答案，输出“Unknown”\n"
        "3) 输出只包含答案本体，不要添加前缀（如“答案是”）\n"
    )


def build_eval_task_suffix(eval_task_type: Optional[str]) -> str:
    t = str(eval_task_type or "").strip().lower()
    if not t:
        return ""
    if t == "adversarial abstention":
        return (
            "\n【评测任务要求】Adversarial Abstention\n"
            "若证据不足以确定答案：输出“Unknown”，不要猜测或补充解释。\n"
        )
    if t == "temporal reasoning":
        return (
            "\n【评测任务要求】Temporal Reasoning\n"
            "只使用证据中的时间/数字进行计算；不要编造任何数字；只输出最终答案。\n"
            "如果证据中已经给出足够的数字/时间，你必须计算并作答，不要输出“Unknown”。\n"
            "若证据确实不足以确定答案：输出“Unknown”。\n"
        )
    if t == "logical event ordering":
        return (
            "\n【评测任务要求】Logical Event Ordering\n"
            "从证据中找出事件并按时间顺序输出；不要添加证据未出现的事件；只输出排序结果。\n"
            "若证据不足以确定完整顺序：输出“Unknown”。\n"
        )
    if t == "information extraction":
        return (
            "\n【评测任务要求】Information Extraction\n"
            "从证据中抽取所需字段并输出；不要改写实体名/数字；只输出抽取结果。\n"
            "若证据中缺失关键字段：输出“Unknown”。\n"
        )
    return ""


def support_check_answer(
    answer: str,
    evidence_text: str,
    question_text: str,
    eval_task_type: Optional[str] = None,
) -> str:
    a = (answer or "").strip()
    if not a:
        return a
    a_lower = a.lower()
    if any(x in a_lower for x in ["unknown", "不确定", "无法确定", "我不确定", "我不知道"]):
        return a
    ev = (evidence_text or "").strip()
    if not ev:
        return a

    t = str(eval_task_type or "").strip().lower()
    if t == "adversarial abstention":
        q = (question_text or "").lower()
        keywords = re.findall(r"[a-z]{4,}", q)
        stop = {"this", "that", "with", "from", "have", "your", "what", "when", "where", "which", "were", "there", "does", "about", "based", "only", "text", "record", "below", "excerpt"}
        keywords = [k for k in keywords if k not in stop]
        if keywords and not any(k in ev.lower() for k in keywords[:12]):
            return "Unknown"

    q_lower = (question_text or "").lower()
    if any(m in q_lower for m in ["year", "month", "date", "when", "时间", "日期", "哪年", "哪天", "什么时候"]):
        digits = re.findall(r"\d{2,4}", a)
        if digits and not all(d in ev for d in digits):
            return "Unknown"

    a_norm = re.sub(r"\s+", " ", a_lower).strip()
    ev_norm = re.sub(r"\s+", " ", ev.lower()).strip()
    if len(a_norm) >= 4 and a_norm not in ev_norm:
        return "Unknown"
    return a


def detect_policy(question: str) -> AnswerPolicyType:
    q = (question or "").strip().lower()
    if "what do you think" in q or "what do you feel" in q or "what do you make of" in q:
        return AnswerPolicyType.REASONING
    if (q.startswith("what ") or q.startswith("which ")) and len(q.split()) <= 20:
        return AnswerPolicyType.STRICT_FACTUAL
    strict_markers = [
        "when",
        "what time",
        "what date",
        "which day",
        "how long",
        "duration",
        "where",
        "what location",
        "which place",
        "who",
        "what name",
        "which person",
        "how many",
        "how much",
        "what number",
        "哪天",
        "什么时候",
        "何时",
        "多久",
        "哪里",
        "什么地方",
        "在哪",
        "谁",
        "什么名字",
        "多少",
        "几个",
        "编号",
        "第几",
        "是否",
        "有没有",
        "发生过",
        "确切",
        "具体",
        "precisely",
        "exactly",
        "specifically",
    ]
    reasoning_markers = [
        "why",
        "how come",
        "analyze",
        "reason",
        "because",
        "motivation",
        "interpret",
        "meaning",
        "significance",
        "relationship",
        "connection",
        "为什么",
        "原因",
        "动机",
        "分析",
        "理解",
        "意义",
        "关系",
        "关联",
        "感受",
        "心情",
        "情绪",
        "如何看",
        "怎么想",
        "影响",
    ]
    if any(m in q for m in reasoning_markers):
        return AnswerPolicyType.REASONING
    if q.startswith(("did ", "have you ", "has ", "was there ", "were there ")):
        return AnswerPolicyType.STRICT_FACTUAL
    if any(m in q for m in strict_markers):
        return AnswerPolicyType.STRICT_FACTUAL
    if len(q.split()) < 15:
        return AnswerPolicyType.STRICT_FACTUAL
    return AnswerPolicyType.REASONING


@dataclass(frozen=True)
class AnswerPolicy:
    name: AnswerPolicyType

    def build_system_suffix(self, context_time: Optional[str]) -> str:
        if self.name == AnswerPolicyType.STRICT_FACTUAL:
            extra = ""
            if context_time:
                extra = (
                    f"\n当前对话时间参考：{context_time}\n"
                    "请将所有相对时间（如 yesterday, last week）转换为基于此日期的绝对时间。\n"
                )
            return (
                "\n【回答风格要求】\n"
                "你正在回答严格事实题：\n"
                "1) 只输出答案本体，不要解释，不要复述问题\n"
                "2) 不能编造；若记忆不足，输出“我不确定”\n"
                "3) 时间必须输出为绝对时间；若问具体日期，输出“D Month YYYY”（如 7 May 2023）；若问年份，只输出 YYYY；禁止包含时刻；禁止相对时间\n"
                f"{extra}"
            )
        return (
            "\n【回答风格要求】\n"
            "你正在回答推理/分析题：\n"
            "1) 可以基于已知事实做推断，但必须明确说明依据\n"
            "2) 不要编造用户未提及的具体细节\n"
        )

    def postprocess(self, raw_answer: str, *, question_text: Optional[str] = None, context_time: Optional[str] = None) -> str:
        s = (raw_answer or "").strip()
        if self.name == AnswerPolicyType.STRICT_FACTUAL:
            s = _LEADING_PREFIX_RE.sub("", s).strip()
            s = s.strip().strip('"\''"“”‘’")
            s = s.rstrip("。.!！?？")
            if question_text and _is_temporal_question(question_text):
                s = postprocess_temporal_answer(s, session_time=context_time, question_text=question_text)
            return s.strip()
        return s


def select_answer_policy(
    question: str,
    explicit: Optional[str],
    eval_mode: bool,
    eval_task_type: Optional[str] = None,
) -> AnswerPolicy:
    if explicit:
        v = str(explicit).strip().lower()
        if v == AnswerPolicyType.STRICT_FACTUAL.value:
            return AnswerPolicy(AnswerPolicyType.STRICT_FACTUAL)
        if v == AnswerPolicyType.REASONING.value:
            return AnswerPolicy(AnswerPolicyType.REASONING)
    if eval_mode:
        if eval_task_type:
            t = str(eval_task_type).strip().lower()
            strict_tasks = {
                "adversarial abstention",
                "temporal reasoning",
                "information extraction",
                "logical event ordering",
            }
            reasoning_tasks = {
                "expert-annotated psychoanalysis",
                "mind-body interaction",
                "mnestic trigger analysis",
            }
            if t in strict_tasks:
                return AnswerPolicy(AnswerPolicyType.STRICT_FACTUAL)
            if t in reasoning_tasks:
                return AnswerPolicy(AnswerPolicyType.REASONING)
        return AnswerPolicy(detect_policy(question))
    return AnswerPolicy(AnswerPolicyType.REASONING)
