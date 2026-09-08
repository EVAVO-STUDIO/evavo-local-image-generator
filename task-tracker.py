#!/usr/bin/env python3
"""
Task history tracking for EVAVO Local Image Generator.
Maintains persistent log of all generation tasks.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

HISTORY_FILE = "task_history.json"

class TaskTracker:
    """Track and manage generation task history."""
    
    def __init__(self, history_file: str = HISTORY_FILE):
        self.history_file = history_file
        self.load_history()
    
    def load_history(self):
        """Load task history from file."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    self.tasks = json.load(f)
            except Exception:
                self.tasks = []
        else:
            self.tasks = []
    
    def save_history(self):
        """Save task history to file."""
        with open(self.history_file, 'w') as f:
            json.dump(self.tasks, f, indent=2)
    
    def add_task(self, task_id: str, prompt: str, status: str = "queued"):
        """Add a new task to history."""
        task = {
            "task_id": task_id,
            "prompt": prompt,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        self.tasks.append(task)
        self.save_history()
    
    def update_task(self, task_id: str, status: str):
        """Update task status."""
        for task in self.tasks:
            if task["task_id"] == task_id:
                task["status"] = status
                task["updated"] = datetime.now().isoformat()
                break
        self.save_history()
    
    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent tasks."""
        return self.tasks[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get task statistics."""
        total = len(self.tasks)
        queued = sum(1 for t in self.tasks if t.get("status") == "queued")
        completed = sum(1 for t in self.tasks if t.get("status") == "completed")
        failed = sum(1 for t in self.tasks if t.get("status") == "failed")
        
        return {
            "total_tasks": total,
            "queued": queued,
            "completed": completed,
            "failed": failed
        }
    
    def clear_history(self):
        """Clear task history."""
        self.tasks = []
        self.save_history()

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Track EVAVO generation tasks")
    parser.add_argument("action", choices=["list", "stats", "clear"], help="Action to perform")
    parser.add_argument("--limit", type=int, default=20, help="Number of tasks to list")
    
    args = parser.parse_args()
    
    tracker = TaskTracker()
    
    if args.action == "list":
        tasks = tracker.list_tasks(args.limit)
        print(f"\nLast {len(tasks)} tasks:\n")
        for task in tasks:
            print(f"  {task['task_id'][:8]}... {task['status']:<10} {task['prompt'][:40]}")
        print()
    
    elif args.action == "stats":
        stats = tracker.get_statistics()
        print("\nTask Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        print()
    
    elif args.action == "clear":
        tracker.clear_history()
        print("Task history cleared.")

if __name__ == "__main__":
    main()
