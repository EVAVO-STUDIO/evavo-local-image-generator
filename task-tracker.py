#!/usr/bin/env python3
"""CLI for the shared EVAVO task history."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from evavo_operations import HISTORY_FILE, TaskTracker


def task_line(task: Dict[str, Any]) -> str:
    task_id = str(task.get("task_id", "N/A"))
    status = str(task.get("status", "unknown"))
    project = str(task.get("project_name", ""))
    prompt = str(task.get("prompt", "")).replace("\n", " ")
    return f"  {task_id[:18]:<18} {status:<10} {project[:18]:<18} {prompt[:50]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Track EVAVO generation tasks")
    subparsers = parser.add_subparsers(dest="action", required=True)

    list_parser = subparsers.add_parser("list", help="List recent tasks")
    list_parser.add_argument("--limit", type=int, default=20, help="Number of tasks to list")
    list_parser.add_argument("--project", help="Filter by project name")
    list_parser.add_argument("--json", action="store_true", help="Emit JSON")

    stats_parser = subparsers.add_parser("stats", help="Display statistics")
    stats_parser.add_argument("--json", action="store_true", help="Emit JSON")

    clear_parser = subparsers.add_parser("clear", help="Clear history")
    clear_parser.add_argument("--yes", action="store_true", help="Required confirmation for non-interactive clearing")

    add_parser = subparsers.add_parser("add", help="Add or upsert a task")
    add_parser.add_argument("task_id")
    add_parser.add_argument("prompt")
    add_parser.add_argument("--project", default="manual")
    add_parser.add_argument("--status", default="queued")

    update_parser = subparsers.add_parser("update", help="Update an existing task")
    update_parser.add_argument("task_id")
    update_parser.add_argument("status")
    update_parser.add_argument("--error-code")
    update_parser.add_argument("--error-message")
    update_parser.add_argument("--output-uri")

    args = parser.parse_args()

    try:
        tracker = TaskTracker()
        if args.action == "list":
            if args.limit < 1:
                parser.error("--limit must be at least 1")
            tasks = tracker.list_tasks(args.limit, project=args.project)
            if args.json:
                print(json.dumps({"history_file": str(HISTORY_FILE), "tasks": tasks}, ensure_ascii=False, indent=2))
            else:
                print(f"\nTask history: {HISTORY_FILE}")
                print(f"Last {len(tasks)} task(s):\n")
                if tasks:
                    print(f"  {'Task ID':<18} {'Status':<10} {'Project':<18} Prompt")
                    print("  " + "-" * 100)
                    for task in tasks:
                        print(task_line(task))
                else:
                    print("  No tasks recorded.")
                print()
            return 0

        if args.action == "stats":
            stats = tracker.get_statistics()
            if args.json:
                print(json.dumps({"history_file": str(HISTORY_FILE), **stats}, indent=2))
            else:
                print(f"\nTask Statistics ({HISTORY_FILE}):")
                for key, value in stats.items():
                    print(f"  {key}: {value}")
                print()
            return 0

        if args.action == "clear":
            if not args.yes:
                print("Refusing to clear task history without --yes.", file=sys.stderr)
                return 2
            tracker.clear_history()
            print(f"Task history cleared: {HISTORY_FILE}")
            return 0

        if args.action == "add":
            task = tracker.add_task(
                args.task_id,
                args.prompt,
                args.status,
                project_name=args.project,
            )
            print(json.dumps(task, ensure_ascii=False, indent=2))
            return 0

        if args.action == "update":
            task = tracker.update_task(
                args.task_id,
                args.status,
                error_code=args.error_code,
                error_message=args.error_message,
                output_uri=args.output_uri,
            )
            print(json.dumps(task, ensure_ascii=False, indent=2))
            return 0

    except KeyError as exc:
        print(f"Task not found: {exc.args[0]}", file=sys.stderr)
        return 4
    except (RuntimeError, OSError, TimeoutError, ValueError) as exc:
        print(f"Task tracker error: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
