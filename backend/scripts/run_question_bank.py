"""Run all public question_bank questions through the backend chat pipeline."""

import json
import sys
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
QUESTION_BANK_PATH = BACKEND_DIR / "data" / "nl2sqlpublic" / "public" / "question_bank.json"
OUTPUT_PATH = ROOT_DIR / "question_bank_results.json"
CHECKPOINT_PATH = ROOT_DIR / "question_bank_results.partial.json"
REQUEST_DELAY_SECONDS = 45
RETRY_WAIT_SECONDS = 75
MAX_ATTEMPTS = 4

sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


def load_question_bank() -> list[dict[str, Any]]:
    return json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))


def normalize_result(payload: dict[str, Any]) -> Any:
    result = payload.get("result", [])
    if isinstance(result, list):
        return result
    return [] if result is None else result


def ensure_two_insights(insights: list[str], result: Any) -> list[str]:
    cleaned = [item for item in insights if isinstance(item, str) and item.strip()]
    if isinstance(result, list):
        row_count = len(result)
        if row_count == 0:
            extras = [
                "查询结果为空，当前筛选条件下没有匹配记录。",
                "由于结果为空，本题无法计算排名、占比或变化类洞察。",
            ]
        else:
            columns = list(result[0].keys()) if isinstance(result[0], dict) else []
            extras = [
                f"查询实际返回 {row_count} 行结果。",
                f"结果字段包括 {', '.join(columns[:6])}。" if columns else "结果为非结构化列表，未识别到字段名。",
            ]
    else:
        extras = [
            "查询结果不是列表结构，已按原始执行结果返回。",
            "当前结果无法进一步计算排名、占比或变化类洞察。",
        ]

    for item in extras:
        if len(cleaned) >= 2:
            break
        if item not in cleaned:
            cleaned.append(item)
    return cleaned[:3]


def to_competition_item(question_item: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    result = normalize_result(payload)
    error = payload.get("error")
    explanation = payload.get("explanation") or ""
    if error:
        explanation = f"{explanation}\n执行错误: {error}".strip()
    return {
        "question_id": question_item.get("question_id", ""),
        "question": question_item.get("question", ""),
        "generated_sql": payload.get("generated_sql") or payload.get("sql") or "",
        "result": result,
        "explanation": explanation,
        "insights": ensure_two_insights(payload.get("insights") or [], result),
    }


def write_json(path: Path, data: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_successful(item: dict[str, Any]) -> bool:
    if not item.get("generated_sql"):
        return False
    explanation = item.get("explanation", "")
    return "Service error:" not in explanation and "HTTP " not in explanation and "后端调用异常" not in explanation


def load_existing_results() -> dict[str, dict[str, Any]]:
    for path in [CHECKPOINT_PATH, OUTPUT_PATH]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            return {item.get("question_id", ""): item for item in data if isinstance(item, dict)}
    return {}


def should_retry(payload: dict[str, Any]) -> bool:
    text = f"{payload.get('error', '')} {payload.get('explanation', '')}"
    retry_markers = [
        "Connection error",
        "System is really busy",
        "RPM limit exceeded",
        "503",
        "429",
    ]
    return any(marker in text for marker in retry_markers)


def call_chat_with_retry(client: TestClient, question: str) -> dict[str, Any]:
    last_payload: dict[str, Any] = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.post("/api/chat", json={"question": question}, timeout=240)
            payload = response.json()
            if response.status_code >= 400:
                payload = {
                    "generated_sql": "",
                    "result": [],
                    "explanation": f"HTTP {response.status_code}: {payload}",
                    "insights": [],
                    "error": f"HTTP {response.status_code}",
                }
        except Exception as exc:
            payload = {
                "generated_sql": "",
                "result": [],
                "explanation": "后端调用异常，未完成该题。",
                "insights": [],
                "error": str(exc),
            }

        last_payload = payload
        if not should_retry(payload):
            return payload

        if attempt < MAX_ATTEMPTS:
            print(f"  retryable model error, wait {RETRY_WAIT_SECONDS}s then retry {attempt + 1}/{MAX_ATTEMPTS}", flush=True)
            time.sleep(RETRY_WAIT_SECONDS)

    return last_payload


def main() -> None:
    questions = load_question_bank()
    client = TestClient(app)
    results: list[dict[str, Any]] = []
    existing_by_id = load_existing_results()

    with client:
        for index, item in enumerate(questions, start=1):
            question = item["question"]
            question_id = item.get("question_id", "")
            existing = existing_by_id.get(question_id)
            if existing and is_successful(existing):
                print(f"[{index}/{len(questions)}] {question_id}: reuse existing successful result", flush=True)
                results.append(existing)
                write_json(CHECKPOINT_PATH, results)
                continue

            started = time.time()
            print(f"[{index}/{len(questions)}] {question_id}: {question}", flush=True)
            payload = call_chat_with_retry(client, question)
            result_item = to_competition_item(item, payload)
            results.append(result_item)
            write_json(CHECKPOINT_PATH, results)
            print(
                f"  done in {time.time() - started:.1f}s, rows="
                f"{len(result_item['result']) if isinstance(result_item['result'], list) else 'n/a'}",
                flush=True,
            )
            if index < len(questions):
                print(f"  wait {REQUEST_DELAY_SECONDS}s to avoid RPM limit", flush=True)
                time.sleep(REQUEST_DELAY_SECONDS)

    write_json(OUTPUT_PATH, results)
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
    print(f"Wrote {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
