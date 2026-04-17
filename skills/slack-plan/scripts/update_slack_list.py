#!/usr/bin/env python3
"""
update_slack_list.py - Slack List 레코드 필드를 업데이트

사용법:
    # 상태 변경 (단건)
    python3 update_slack_list.py F0AQE9DGEDU --record Rec0AR1Q62RFH --status "백엔드 배포완료"

    # 상태 변경 (다건)
    python3 update_slack_list.py F0AQE9DGEDU --record Rec0AR1Q62RFH Rec0ARH79LC1G --status "완료"

    # 상태 변경 (stdin JSON 배열)
    echo '["Rec0AR1Q62RFH","Rec0ARH79LC1G"]' | python3 update_slack_list.py F0AQE9DGEDU --status "완료"

    # 텍스트 필드 업데이트 (동일 값)
    python3 update_slack_list.py F0AQE9DGEDU --record Rec0AR1Q62RFH --field "비고" --value "작업 완료"

    # 텍스트 필드 비우기
    python3 update_slack_list.py F0AQE9DGEDU --record Rec0AR1Q62RFH --field "비고" --clear

    # 텍스트 필드 업데이트 (레코드별 다른 값, stdin)
    cat <<'EOF' | python3 update_slack_list.py F0AQE9DGEDU --field "백엔드 변경 사항"
    [
      {"record_id": "Rec0AR1Q62RFH", "value": "[Task Review] 배포완료..."},
      {"record_id": "Rec0ARH79LC1G", "value": "[Task Review] 배포완료..."}
    ]
    EOF

필요 권한:
    - lists:write (Bot/User token)
    - lists:read (Bot/User token) - 스키마 조회용
    - files:read (Bot/User token) - 스키마 조회용

API:
    - files.info: 스키마 조회 (컬럼 ID, select 옵션)
    - slackLists.items.update: 셀 업데이트 (select, rich_text)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SLACK_API_BASE = "https://slack.com/api"
REQUEST_TIMEOUT = 30
BATCH_SIZE = 4


def load_harness_config():
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
    for var in ("SLACK_BOT_TOKEN", "SLACK_USER_TOKEN", "SLACK_TOKEN"):
        token = os.environ.get(var)
        if token:
            return token
    return None


def parse_list_id(input_str):
    input_str = input_str.strip()
    url_match = re.search(r"/lists/[A-Z0-9]+/([A-Z0-9]+)", input_str)
    if url_match:
        return url_match.group(1)
    if re.match(r"^[A-Z][A-Z0-9]{8,}$", input_str):
        return input_str
    return None


def slack_api(method, token, params=None, use_get=False):
    if use_get and params:
        qs = urllib.parse.urlencode(params)
        url = f"{SLACK_API_BASE}/{method}?{qs}"
        data = None
    else:
        url = f"{SLACK_API_BASE}/{method}"
        data = json.dumps(params).encode("utf-8") if params else None
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
        die(f"Slack API 에러 (HTTP {e.code}): {body_text}")
    except urllib.error.URLError as e:
        die(f"네트워크 에러: {e.reason}")
    except TimeoutError:
        die(f"요청 타임아웃 ({REQUEST_TIMEOUT}초)")

    if not body.get("ok"):
        error = body.get("error", "unknown_error")
        needed = body.get("needed", "")
        detail = body.get("response_metadata", {}).get("messages", [])
        msg = f"Slack API 에러: {error}"
        if needed:
            msg += f" (needed: {needed})"
        if detail:
            msg += f"\n상세: {', '.join(detail)}"
        die(msg)

    return body


def fetch_schema(token, list_id):
    resp = slack_api("files.info", token, {"file": list_id}, use_get=True)
    return resp.get("file", {}).get("list_metadata", {}).get("schema", [])


def find_column(schema, name_or_id):
    for col in schema:
        if (
            col["name"] == name_or_id
            or col["id"] == name_or_id
            or col["key"] == name_or_id
        ):
            return col
    return None


def find_select_option(col, label):
    for choice in col.get("options", {}).get("choices", []):
        if choice["label"] == label:
            return choice["value"]
    return None


def build_text_cell(row_id, column_id, text):
    if not text:
        return {"row_id": row_id, "column_id": column_id, "rich_text": []}
    return {
        "row_id": row_id,
        "column_id": column_id,
        "rich_text": [
            {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": text}],
                    }
                ],
            }
        ],
    }


def build_select_cell(row_id, column_id, option_value):
    return {"row_id": row_id, "column_id": column_id, "select": [option_value]}


def send_batch(token, list_id, cells):
    success = 0
    for i in range(0, len(cells), BATCH_SIZE):
        batch = cells[i : i + BATCH_SIZE]
        slack_api(
            "slackLists.items.update", token, {"list_id": list_id, "cells": batch}
        )
        success += len(batch)
        info(f"  배치 {i // BATCH_SIZE + 1}: {len(batch)}셀 업데이트")
        if i + BATCH_SIZE < len(cells):
            time.sleep(0.5)
    return success


def info(msg):
    print(f"[update-slack-list] {msg}", file=sys.stderr)


def die(msg):
    print(f"\n[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Slack List 레코드 업데이트",
        epilog='예시: python3 update_slack_list.py F0AQE9DGEDU --record Rec... --status "완료"',
    )
    parser.add_argument("list_input", help="Slack List URL 또는 ID")
    parser.add_argument(
        "--record", nargs="+", help="대상 레코드 ID (미지정 시 stdin JSON)"
    )
    parser.add_argument(
        "--status", help='변경할 상태 라벨 (예: "완료", "백엔드 배포완료")'
    )
    parser.add_argument("--field", help="변경할 텍스트 컬럼 이름")
    parser.add_argument("--value", help="텍스트 컬럼에 넣을 값")
    parser.add_argument("--clear", action="store_true", help="텍스트 컬럼 비우기")
    args = parser.parse_args()

    load_harness_config()
    token = get_token()
    if not token:
        die("Slack 토큰 없음. .harness/config.env에 SLACK_BOT_TOKEN을 설정하세요.")

    list_id = parse_list_id(args.list_input)
    if not list_id:
        die(f"유효하지 않은 List ID: {args.list_input}")

    if not args.status and not args.field:
        die("--status 또는 --field 중 하나를 지정하세요.")

    values_map = {}
    if args.record:
        record_ids = args.record
    elif not sys.stdin.isatty():
        stdin_data = json.load(sys.stdin)
        if isinstance(stdin_data, list) and stdin_data:
            if isinstance(stdin_data[0], str):
                record_ids = stdin_data
            elif isinstance(stdin_data[0], dict):
                record_ids = [r["record_id"] for r in stdin_data]
                values_map = {r["record_id"]: r.get("value", "") for r in stdin_data}
            else:
                die(
                    'stdin JSON: ["RecID", ...] 또는 [{"record_id":..., "value":...}] 형식'
                )
        else:
            die("stdin JSON이 비어 있거나 배열이 아닙니다.")
    else:
        die("--record 또는 stdin으로 레코드 ID를 지정하세요.")

    info(f"List: {list_id}, 대상 레코드: {len(record_ids)}건")

    schema = fetch_schema(token, list_id)
    cells = []

    if args.status:
        status_col = None
        for col in schema:
            if col["type"] == "select":
                status_col = col
                break
        if not status_col:
            die("select 타입 컬럼을 찾을 수 없습니다.")

        option_value = find_select_option(status_col, args.status)
        if not option_value:
            labels = [
                c["label"] for c in status_col.get("options", {}).get("choices", [])
            ]
            die(f"상태 '{args.status}' 없음. 가능한 값: {labels}")

        for rid in record_ids:
            cells.append(build_select_cell(rid, status_col["id"], option_value))
        info(f"상태 변경: '{args.status}' ({option_value})")

    if args.field:
        col = find_column(schema, args.field)
        if not col:
            names = [c["name"] for c in schema]
            die(f"컬럼 '{args.field}' 없음. 가능한 값: {names}")

        for rid in record_ids:
            if args.clear:
                cells.append(build_text_cell(rid, col["id"], ""))
            elif args.value:
                cells.append(build_text_cell(rid, col["id"], args.value))
            elif rid in values_map:
                cells.append(build_text_cell(rid, col["id"], values_map[rid]))
            else:
                info(f"  [SKIP] {rid}: --value 또는 stdin value 없음")

        action = "비우기" if args.clear else "업데이트"
        info(f"필드 '{args.field}' {action}")

    if not cells:
        die("업데이트할 셀이 없습니다.")

    count = send_batch(token, list_id, cells)

    result = {"ok": True, "updated_cells": count, "record_count": len(record_ids)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    info(f"완료. {count}셀 업데이트.")


if __name__ == "__main__":
    main()
