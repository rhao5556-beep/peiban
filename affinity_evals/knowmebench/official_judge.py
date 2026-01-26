import argparse
import asyncio
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openai


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.llm import normalize_openai_base_url


@dataclass
class JudgeResult:
    item_id: int
    task_type: str
    score: int
    reasoning: str
    status: str


def _rubric(task_type: str) -> str:
    common = """你是严格的评测裁判。给定 question/reference_answer/model_answer，输出 0-5 整数分数与简短理由。

输出必须是 JSON：{"score": <0-5>, "reasoning": "<...>"}。不要输出多余文本。

通用原则：
- 以 reference_answer 为准。
- 若 reference_answer 表示“不存在/未知/文本未提及”，模型应明确拒答/不知道，且不得编造；编造应重罚。
- 只评测“是否按任务要求回答正确”，不要奖励文采。
"""
    t = (task_type or "").strip()
    if t == "Information Extraction":
        return (
            common
            + """
任务：实体/事实抽取，要求精准命中 reference_answer。
评分：
5=关键事实完全正确且无多余编造；3=部分正确/轻微偏差；1=大部分错误或凭空补全；0=严重编造或与参考相反。
"""
        )
    if t == "Adversarial Abstention":
        return (
            common
            + """
任务：对“陷阱问题”必须克制。reference_answer 若为“不存在/未知”，模型必须明确表示不知道/文本未提及。
评分：
5=明确拒答/不知道且不编造；3=基本拒答但夹带猜测；1=明显猜测/脑补；0=自信编造具体细节。
"""
        )
    if t == "Temporal Reasoning":
        return (
            common
            + """
任务：时间/持续时长/先后顺序推理。以 reference_answer 的时间逻辑为准。
评分：
5=推理链与答案完全正确；3=大体正确但有单位/细节误差；1=时间逻辑错误；0=胡乱编造。
"""
        )
    if t == "Logical Event Ordering":
        return (
            common
            + """
任务：按参考要求对事件排序（例如危险升级、语义维度等）。以 reference_answer 的顺序为准。
评分：
5=顺序一致；3=仅少量相邻交换；1=顺序大错；0=完全不相关或编造新事件。
"""
        )
    if t == "Mnestic Trigger Analysis":
        return (
            common
            + """
任务：识别触发回忆的线索/感官提示等。以 reference_answer 的要点为准。
评分：
5=核心触发因素准确；3=抓到部分要点；1=基本跑题；0=纯编造。
"""
        )
    if t == "Mind-Body Interaction":
        return (
            common
            + """
任务：解释心理-生理/行为矛盾与内在动因。以 reference_answer 的解释框架为准。
评分：
5=解释高度贴合参考；3=解释合理但关键点缺失；1=解释明显偏离；0=胡编乱造。
"""
        )
    if t == "Expert-Annotated Psychoanalysis":
        return (
            common
            + """
任务：较深层的心理动机/身份/关系洞察。以 reference_answer 的分析为准。
评分：
5=关键洞察与参考一致；3=部分一致但有偏差；1=泛泛而谈/偏离；0=与参考相反或编造。
"""
        )
    return common + "\n任务类型未知：按 reference_answer 对齐程度评分。\n"


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("judge_output_not_json")
    return json.loads(m.group(0))


async def _judge_one(
    client: openai.AsyncOpenAI,
    judge_model: str,
    item: dict[str, Any],
    sem: asyncio.Semaphore,
) -> JudgeResult:
    async with sem:
        item_id = int(item.get("id"))
        task_type = str(item.get("task_type") or "")
        question = str(item.get("question") or "")
        reference_answer = str(item.get("reference_answer") or "")
        model_answer = str(item.get("model_answer") or "")

        content = json.dumps(
            {
                "id": item_id,
                "task_type": task_type,
                "question": question,
                "reference_answer": reference_answer,
                "model_answer": model_answer,
            },
            ensure_ascii=False,
        )

        last_error: Exception | None = None
        for attempt in range(7):
            try:
                resp = await client.chat.completions.create(
                    model=judge_model,
                    messages=[
                        {"role": "system", "content": _rubric(task_type)},
                        {"role": "user", "content": content},
                    ],
                    temperature=0.0,
                    max_tokens=300,
                    stream=False,
                )
                out = resp.choices[0].message.content or ""
                data = _extract_json(out)
                score = int(data.get("score"))
                score = max(0, min(5, score))
                reasoning = str(data.get("reasoning") or "")
                return JudgeResult(
                    item_id=item_id,
                    task_type=task_type,
                    score=score,
                    reasoning=reasoning,
                    status="ok",
                )
            except Exception as e:
                last_error = e
                msg = str(e)
                is_ratelimit = e.__class__.__name__ == "RateLimitError" or "rate limit" in msg.lower() or "429" in msg
                if not is_ratelimit or attempt >= 6:
                    break
                base = 1.5**attempt
                jitter = random.random() * 0.5
                await asyncio.sleep(min(30.0, base + jitter))

        return JudgeResult(
            item_id=item_id,
            task_type=task_type,
            score=0,
            reasoning=f"Evaluation Error: {last_error.__class__.__name__}: {last_error}",
            status="error",
        )


def _load_items(input_dir: Path) -> list[dict[str, Any]]:
    files = sorted(input_dir.glob("*.model_outputs.json"))
    if not files:
        raise FileNotFoundError(f"no model_outputs found under {input_dir}")
    items: list[dict[str, Any]] = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"invalid model_outputs format: {f}")
        items.extend(data)
    return items


async def _main_async(args: argparse.Namespace) -> int:
    input_dir = Path(args.input_dir).resolve()
    out_file = Path(args.output_file).resolve()

    items = _load_items(input_dir)

    base_url = normalize_openai_base_url(args.openai_base_url or settings.OPENAI_API_BASE)
    api_key = args.openai_api_key or settings.OPENAI_API_KEY
    judge_model = args.judge_model or settings.OPENAI_MODEL

    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    sem = asyncio.Semaphore(int(args.concurrency))
    tasks = [asyncio.create_task(_judge_one(client, judge_model, it, sem)) for it in items]
    results = await asyncio.gather(*tasks)

    ok = [r for r in results if r.status == "ok"]
    avg = (sum(r.score for r in ok) / len(ok)) if ok else 0.0

    payload = {
        "meta": {
            "judge_model": judge_model,
            "openai_base_url": base_url,
            "total_items": len(results),
            "evaluated_items": len(ok),
            "average_score": avg,
        },
        "details": [
            {
                "id": r.item_id,
                "task_type": r.task_type,
                "score": r.score,
                "reasoning": r.reasoning,
                "status": r.status,
            }
            for r in results
        ],
    }

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload["meta"], ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", default=str(Path("outputs/knowmebench_run/ds1_graph_only_limit5_all7").resolve()))
    parser.add_argument(
        "--output_file",
        default=str(Path("outputs/knowmebench_run/ds1_graph_only_limit5_all7/judge.results.json").resolve()),
    )
    parser.add_argument("--judge_model", default="")
    parser.add_argument("--openai_base_url", default="")
    parser.add_argument("--openai_api_key", default="")
    parser.add_argument("--concurrency", default="4")
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())

