#!/usr/bin/env python3
"""
fetch_slack_list.py - Slack List 레코드를 조회하여 정규화 JSON으로 출력

사용법:
    python3 fetch_slack_list.py <SLACK_LIST_URL_OR_ID>
    python3 fetch_slack_list.py F0AQE9DGEDU
    python3 fetch_slack_list.py F0AQE9DGEDU --status "새 항목"
    python3 fetch_slack_list.py F0AQE9DGEDU --exclude-status 완료 "백엔드 배포완료" 이슈아님

필요 권한:
    - lists:read (Bot/User token)
    - files:read (Bot/User token)

환경변수 (우선순위 순):
    1. SLACK_BOT_TOKEN
    2. SLACK_USER_TOKEN
    3. SLACK_TOKEN

API:
    - files.info: 리스트 스키마 (컬럼 정의, select 옵션)
    - lists.records.list: 전체 레코드 + 필드값
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SLACK_API_BASE = "https://slack.com/api"
REQUEST_TIMEOUT = 30


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


def fetch_records(token, list_id):
    resp = slack_api("lists.records.list", token, {"list_id": list_id})
    return resp.get("records", [])


def build_select_map(schema):
    select_maps = {}
    for col in schema:
        if col["type"] == "select":
            choices = col.get("options", {}).get("choices", [])
            mapping = {c["value"]: c["label"] for c in choices}
            select_maps[col["key"]] = mapping
            select_maps[col["id"]] = mapping
    return select_maps


def normalize_records(records, schema, select_maps):
    items = []
    for rec in records:
        item = {"_record_id": rec["id"]}
        fields = {f["key"]: f for f in rec.get("fields", [])}

        for col in schema:
            key = col["key"]
            name = col["name"]
            field = fields.get(key, {})

            if col["type"] == "select":
                raw = field.get("value", "")
                mapping = select_maps.get(key, {})
                item[name] = mapping.get(raw, raw)
            elif col["type"] == "date":
                item[name] = field.get("value", "")
            elif key == "name":
                item[name] = fields.get("name", {}).get("text", "")
            elif col["type"] in ("todo_completed", "todo_assignee", "todo_due_date"):
                item[name] = field.get("value", "")
            else:
                item[name] = field.get("text", "")

        items.append(item)
    return items


def info(msg):
    print(f"[fetch-slack-list] {msg}", file=sys.stderr)


def die(msg):
    print(f"\n[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Slack List 레코드 조회",
        epilog="예시: python3 fetch_slack_list.py https://tokdev.slack.com/lists/T01K68TCW6A/F0AQE9DGEDU",
    )
    parser.add_argument("input", help="Slack List URL 또는 ID")
    parser.add_argument("--status", nargs="+", help="해당 상태만 필터링")
    parser.add_argument("--exclude-status", nargs="+", help="해당 상태 제외")
    args = parser.parse_args()

    load_harness_config()
    token = get_token()
    if not token:
        die(
            "Slack 토큰이 설정되지 않았습니다.\n"
            ".harness/config.env에 SLACK_BOT_TOKEN을 설정하거나,\n"
            "환경변수를 설정하세요: export SLACK_BOT_TOKEN=xoxb-..."
        )

    list_id = parse_list_id(args.input)
    if not list_id:
        die(f"유효하지 않은 Slack List URL/ID: {args.input}")

    info(f"List ID: {list_id}")

    schema = fetch_schema(token, list_id)
    select_maps = build_select_map(schema)
    records = fetch_records(token, list_id)
    items = normalize_records(records, schema, select_maps)

    info(f"전체 레코드: {len(items)}건")

    status_col = None
    for col in schema:
        if col["type"] == "select":
            status_col = col["name"]
            break

    if status_col and args.status:
        items = [i for i in items if i.get(status_col) in args.status]
        info(f"필터링 후: {len(items)}건 (status in {args.status})")
    if status_col and args.exclude_status:
        items = [i for i in items if i.get(status_col) not in args.exclude_status]
        info(f"필터링 후: {len(items)}건 (status not in {args.exclude_status})")

    output = {
        "metadata": {
            "list_id": list_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "total_items": len(items),
            "status_column": status_col,
            "schema": [
                {"name": c["name"], "id": c["id"], "key": c["key"], "type": c["type"]}
                for c in schema
            ],
            "select_options": {
                col["name"]: [
                    {"label": c["label"], "value": c["value"]}
                    for c in col.get("options", {}).get("choices", [])
                ]
                for col in schema
                if col["type"] == "select"
            },
        },
        "items": items,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    info(f"완료. {len(items)}건 출력.")


if __name__ == "__main__":
    main()
