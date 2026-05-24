"""Collect question_bank answers from a running local backend API."""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
QUESTION_BANK_PATH = ROOT_DIR / "backend" / "data" / "nl2sqlpublic" / "public" / "question_bank.json"
OUTPUT_PATH = ROOT_DIR / "question_bank_results.json"
PARTIAL_PATH = ROOT_DIR / "question_bank_results.partial.json"
CHAT_URL = "http://localhost:8001/api/chat"
HEALTH_URL = "http://localhost:8001/health"

REQUEST_DELAY_SECONDS = int(os.getenv("QB_REQUEST_DELAY_SECONDS", "2"))
RETRY_DELAY_SECONDS = int(os.getenv("QB_RETRY_DELAY_SECONDS", "10"))
MAX_ATTEMPTS = int(os.getenv("QB_MAX_ATTEMPTS", "1"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def post_json(url: str, payload: dict[str, Any], timeout: int = 240) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_health() -> dict[str, Any]:
    with urllib.request.urlopen(HEALTH_URL, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def should_retry(payload: dict[str, Any]) -> bool:
    text = f"{payload.get('error', '')} {payload.get('explanation', '')}"
    return any(marker in text for marker in ["Connection error", "System is really busy", "RPM limit exceeded", "503", "429"])


def is_successful(item: dict[str, Any]) -> bool:
    if not item.get("generated_sql"):
        return False
    text = f"{item.get('explanation', '')}"
    return "Service error:" not in text and "HTTP " not in text and "调用异常" not in text


def load_existing() -> dict[str, dict[str, Any]]:
    for path in [PARTIAL_PATH, OUTPUT_PATH]:
        if not path.exists():
            continue
        try:
            data = read_json(path)
        except Exception:
            continue
        if isinstance(data, list):
            return {item.get("question_id", ""): item for item in data if isinstance(item, dict)}
    return {}


def ensure_two_insights(insights: Any, result: Any) -> list[str]:
    cleaned = [item.strip() for item in insights or [] if isinstance(item, str) and item.strip()]
    if len(cleaned) >= 2:
        return cleaned[:3]

    if isinstance(result, list) and result:
        columns = list(result[0].keys()) if isinstance(result[0], dict) else []
        additions = [
            f"查询实际返回 {len(result)} 行结果。",
            f"结果字段包括 {', '.join(columns[:6])}。" if columns else "结果为列表结构，但未识别到字段名。",
        ]
    elif isinstance(result, list):
        additions = [
            "查询结果为空，当前筛选条件下没有匹配记录。",
            "空结果来自 SQL 实际执行结果，未生成排名、占比或变化类洞察。",
        ]
    else:
        additions = [
            "查询返回非列表结果，已按后端原始结果写入。",
            "当前结果无法计算排名、占比或变化类洞察。",
        ]

    for item in additions:
        if len(cleaned) >= 2:
            break
        if item not in cleaned:
            cleaned.append(item)
    return cleaned[:3]


def normalize_item(question_item: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result", [])
    if result is None:
        result = []
    explanation = payload.get("explanation") or ""
    if payload.get("error"):
        explanation = f"{explanation}\n执行错误: {payload['error']}".strip()
    return {
        "question_id": question_item.get("question_id", ""),
        "question": question_item.get("question", ""),
        "generated_sql": payload.get("generated_sql") or payload.get("sql") or "",
        "result": result,
        "explanation": explanation,
        "insights": ensure_two_insights(payload.get("insights"), result),
    }


def call_with_retry(question: str) -> dict[str, Any]:
    last_payload: dict[str, Any] = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            payload = post_json(CHAT_URL, {"question": question})
        except urllib.error.HTTPError as exc:
            payload = {
                "generated_sql": "",
                "result": [],
                "explanation": f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')}",
                "insights": [],
                "error": f"HTTP {exc.code}",
            }
        except Exception as exc:
            payload = {
                "generated_sql": "",
                "result": [],
                "explanation": "调用本地后端接口异常，未完成该题。",
                "insights": [],
                "error": str(exc),
            }

        last_payload = payload
        if not should_retry(payload):
            return payload
        if attempt < MAX_ATTEMPTS:
            print(f"  retryable error, wait {RETRY_DELAY_SECONDS}s ({attempt + 1}/{MAX_ATTEMPTS})", flush=True)
            time.sleep(RETRY_DELAY_SECONDS)
    return last_payload


def main() -> None:
    health = get_health()
    print(f"Local backend ok: {health.get('service')} {health.get('models', {}).get('llm', {}).get('model')}", flush=True)

    questions = read_json(QUESTION_BANK_PATH)
    existing = load_existing()
    results: list[dict[str, Any]] = []

    for index, question_item in enumerate(questions, start=1):
        question_id = question_item.get("question_id", "")
        previous = existing.get(question_id)
        if previous and is_successful(previous):
            print(f"[{index}/{len(questions)}] {question_id}: reuse existing success", flush=True)
            results.append(previous)
            write_json(PARTIAL_PATH, results)
            continue

        print(f"[{index}/{len(questions)}] {question_id}: {question_item.get('question')}", flush=True)
        started = time.time()
        payload = call_with_retry(question_item["question"])
        item = normalize_item(question_item, payload)
        results.append(item)
        write_json(PARTIAL_PATH, results)
        row_count = len(item["result"]) if isinstance(item["result"], list) else "n/a"
        print(f"  done in {time.time() - started:.1f}s, rows={row_count}, sql={'yes' if item['generated_sql'] else 'no'}", flush=True)

        if index < len(questions):
            time.sleep(REQUEST_DELAY_SECONDS)

    write_json(OUTPUT_PATH, results)
    if PARTIAL_PATH.exists():
        PARTIAL_PATH.unlink()
    print(f"Wrote {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
