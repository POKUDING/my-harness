#!/usr/bin/env python3
"""
fetch_slack_list.py - Slack List를 CSV로 다운로드하고 정규화 JSON으로 변환

사용법:
    python3 fetch_slack_list.py <SLACK_LIST_URL_OR_ID> [--output-dir DIR]

예시:
    python3 fetch_slack_list.py https://tokdev.slack.com/lists/T01K68TCW6A/F0AQE9DGEDU
    python3 fetch_slack_list.py F0AQE9DGEDU --output-dir ./data

필요 권한:
    - lists:read (Bot/User token)
    Slack App에서 OAuth Scopes에 lists:read를 추가해야 합니다.

환경변수 (우선순위 순):
    1. SLACK_BOT_TOKEN
    2. SLACK_USER_TOKEN
    3. SLACK_TOKEN
"""

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SLACK_API_BASE = "https://slack.com/api"
EXPORT_POLL_INTERVAL = 2  # seconds
EXPORT_MAX_WAIT = 120  # seconds
REQUEST_TIMEOUT = 30  # seconds


def load_harness_config():
    """프로젝트 루트의 .harness/config.env에서 설정을 로드한다.
    config.env 값이 항상 우선 적용된다 (기존 환경변수를 덮어씀).
    """
    path = Path.cwd()
    for _ in range(5):
        config_file = path / ".harness" / "config.env"
        if config_file.exists():
            with open(config_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        os.environ[key.strip()] = val.strip()
            return
        path = path.parent


def get_token():
    """환경변수에서 Slack 토큰을 우선순위 순으로 가져온다."""
    for var in ("SLACK_BOT_TOKEN", "SLACK_USER_TOKEN", "SLACK_TOKEN"):
        token = os.environ.get(var)
        if token:
            return token
    return None


def parse_list_id(input_str):
    """Slack List URL 또는 list_id에서 list_id를 추출한다.

    지원 형식:
        - https://workspace.slack.com/lists/T.../F0AQE9DGEDU
        - https://app.slack.com/lists/T.../F0AQE9DGEDU
        - F0AQE9DGEDU (직접 ID)
    """
    input_str = input_str.strip()

    # URL 형식: /lists/T.../F...
    url_match = re.search(r"/lists/[A-Z0-9]+/([A-Z0-9]+)", input_str)
    if url_match:
        return url_match.group(1)

    # 직접 ID 형식: F로 시작하는 대문자+숫자
    if re.match(r"^[A-Z][A-Z0-9]{8,}$", input_str):
        return input_str

    return None


def slack_api_call(method, token, params=None):
    """Slack Web API를 호출한다."""
    url = f"{SLACK_API_BASE}/{method}"

    if params:
        data = json.dumps(params).encode("utf-8")
    else:
        data = None

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            die(f"인증 실패 (HTTP 401). 토큰이 유효한지 확인하세요.\n응답: {body_text}")
        elif e.code == 403:
            die(f"권한 부족 (HTTP 403). lists:read 스코프가 필요합니다.\n응답: {body_text}")
        elif e.code == 429:
            retry_after = e.headers.get("Retry-After", "60")
            die(f"Rate limit 초과. {retry_after}초 후 재시도하세요.")
        else:
            die(f"Slack API 에러 (HTTP {e.code}): {body_text}")
    except urllib.error.URLError as e:
        die(f"네트워크 에러: {e.reason}")
    except TimeoutError:
        die(f"요청 타임아웃 ({REQUEST_TIMEOUT}초). 네트워크 상태를 확인하세요.")

    if not body.get("ok"):
        error = body.get("error", "unknown_error")
        error_messages = {
            "not_authed": "토큰이 설정되지 않았습니다.",
            "invalid_auth": "토큰이 유효하지 않습니다.",
            "missing_scope": f"필요 권한이 없습니다. lists:read 스코프를 추가하세요. (needed: {body.get('needed', 'unknown')})",
            "list_not_found": "해당 리스트를 찾을 수 없습니다. URL/ID를 확인하세요.",
            "access_denied": "이 리스트에 대한 접근 권한이 없습니다.",
            "export_not_found": "내보내기 작업을 찾을 수 없습니다.",
        }
        msg = error_messages.get(error, f"Slack API 에러: {error}")
        detail = body.get("response_metadata", {}).get("messages", [])
        if detail:
            msg += f"\n상세: {', '.join(detail)}"
        die(msg)

    return body


def start_export(token, list_id):
    """비동기 CSV 내보내기를 시작한다."""
    info(f"리스트 {list_id} 내보내기 시작...")
    return slack_api_call(
        "lists.export.csvAsync.start",
        token,
        {"list_id": list_id},
    )


def poll_export_status(token, list_id, export_id):
    """내보내기 완료를 대기한다."""
    elapsed = 0
    while elapsed < EXPORT_MAX_WAIT:
        resp = slack_api_call(
            "lists.export.csvAsync.getStatus",
            token,
            {"list_id": list_id, "export_id": export_id},
        )

        status = resp.get("status", "unknown")
        info(f"  내보내기 상태: {status} ({elapsed}초 경과)")

        if status == "completed":
            return resp
        elif status == "failed":
            die(f"내보내기 실패: {resp.get('error', 'unknown')}")

        time.sleep(EXPORT_POLL_INTERVAL)
        elapsed += EXPORT_POLL_INTERVAL

    die(f"내보내기 타임아웃 ({EXPORT_MAX_WAIT}초). 리스트가 너무 크거나 Slack 서버 문제일 수 있습니다.")


def download_csv(url):
    """완료된 CSV를 다운로드한다."""
    info("CSV 다운로드 중...")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        die(f"CSV 다운로드 실패: {e}")


def csv_to_items(csv_text):
    """CSV 텍스트를 정규화된 아이템 리스트로 변환한다."""
    reader = csv.DictReader(io.StringIO(csv_text))
    items = []
    for row in reader:
        item = {}
        for key, value in row.items():
            clean_key = key.strip().lower().replace(" ", "_")
            item[clean_key] = value.strip() if value else ""
        items.append(item)
    return items


def build_normalized_json(list_id, items, csv_text):
    """Claude가 읽기 좋은 정규화 JSON을 생성한다."""
    return {
        "metadata": {
            "list_id": list_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "total_items": len(items),
            "columns": list(items[0].keys()) if items else [],
        },
        "items": items,
        "raw_csv_lines": len(csv_text.strip().split("\n")),
    }


def save_outputs(output_dir, list_id, csv_text, normalized):
    """CSV 원문과 정규화 JSON을 저장한다."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / f"slack-list-{list_id}-raw.csv"
    json_path = output_dir / f"slack-list-{list_id}.json"

    csv_path.write_text(csv_text, encoding="utf-8")
    info(f"CSV 저장: {csv_path}")

    json_text = json.dumps(normalized, ensure_ascii=False, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    info(f"JSON 저장: {json_path}")

    return str(csv_path), str(json_path)


def info(msg):
    print(f"[slack-list-plan] {msg}", file=sys.stderr)


def die(msg):
    print(f"\n[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Slack List를 CSV로 다운로드하고 정규화 JSON으로 변환",
        epilog="예시: python3 fetch_slack_list.py https://tokdev.slack.com/lists/T01K68TCW6A/F0AQE9DGEDU",
    )
    parser.add_argument(
        "input",
        help="Slack List URL (https://...slack.com/lists/T.../F...) 또는 list_id (F...)",
    )
    parser.add_argument(
        "--output-dir",
        default=".claude/skills/slack-list-plan/data",
        help="출력 디렉토리 (기본: .claude/skills/slack-list-plan/data)",
    )
    args = parser.parse_args()

    # 1. 토큰 확인 (.harness/config.env → 환경변수 순으로 탐색)
    load_harness_config()
    token = get_token()
    if not token:
        die(
            "Slack 토큰이 설정되지 않았습니다.\n"
            "/harness-setup 을 실행하여 토큰을 저장하거나,\n"
            "다음 환경변수 중 하나를 설정하세요:\n"
            "  export SLACK_BOT_TOKEN=xoxb-...\n"
            "  export SLACK_USER_TOKEN=xoxp-..."
        )

    # 2. List ID 파싱
    list_id = parse_list_id(args.input)
    if not list_id:
        die(
            f"유효하지 않은 Slack List URL/ID: {args.input}\n"
            "올바른 형식:\n"
            "  URL: https://workspace.slack.com/lists/T.../F...\n"
            "  ID:  F0AQE9DGEDU"
        )

    info(f"List ID: {list_id}")

    # 3. 비동기 CSV 내보내기 시작
    export_resp = start_export(token, list_id)
    export_id = export_resp.get("export_id")
    if not export_id:
        die("내보내기 시작 응답에 export_id가 없습니다. Slack API 응답을 확인하세요.")

    # 4. 내보내기 완료 대기
    status_resp = poll_export_status(token, list_id, export_id)
    download_url = status_resp.get("download_url")
    if not download_url:
        die("내보내기 완료 응답에 download_url이 없습니다.")

    # 5. CSV 다운로드
    csv_text = download_csv(download_url)
    if not csv_text.strip():
        die("다운로드된 CSV가 비어 있습니다. 리스트에 아이템이 있는지 확인하세요.")

    # 6. 정규화
    items = csv_to_items(csv_text)
    if not items:
        die("CSV 파싱 결과가 비어 있습니다. CSV 형식을 확인하세요.")

    normalized = build_normalized_json(list_id, items, csv_text)

    # 7. 저장
    csv_path, json_path = save_outputs(args.output_dir, list_id, csv_text, normalized)

    # 8. stdout으로 JSON 출력 (Claude에 주입용)
    print(json.dumps(normalized, ensure_ascii=False, indent=2))

    info(f"완료. {len(items)}개 아이템 처리됨.")


if __name__ == "__main__":
    main()
