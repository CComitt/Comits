import os
import sys
import time
import argparse
import subprocess
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

DEFAULT_WORKERS = 4
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0

lock = threading.Lock()
completed_count = 0


def parse_args():
    parser = argparse.ArgumentParser(description="Bulk empty git commit tool")
    parser.add_argument("count", type=int, help="Number of commits to create")
    parser.add_argument("--push", action="store_true", help="Push after committing")
    parser.add_argument("--prefix", type=str, default="Commit", help="Commit message prefix")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel worker threads")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retry attempts per commit")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without making commits")
    parser.add_argument("--timestamp", action="store_true", help="Include timestamp in commit message")
    return parser.parse_args()


def run_git(command, retries, retry_delay):
    for attempt in range(retries):
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            return True
        if attempt < retries - 1:
            time.sleep(retry_delay)
    return False


def build_message(prefix, index, total, use_timestamp):
    if use_timestamp:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{prefix} {index} of {total} [{ts}]"
    return f"{prefix} {index} of {total}"


def make_commit(index, total, prefix, retries, retry_delay, dry_run, use_timestamp):
    global completed_count
    message = build_message(prefix, index, total, use_timestamp)
    if not dry_run:
        success = run_git(["git", "commit", "--allow-empty", "-m", message], retries, retry_delay)
    else:
        success = True
    with lock:
        completed_count += 1
        percent = (completed_count / total) * 100
        bar_filled = int(percent / 2)
        bar = "█" * bar_filled + "░" * (50 - bar_filled)
        status = "✓" if success else "✗"
        sys.stdout.write(f"\r[{bar}] {percent:.1f}% {status} {completed_count}/{total}")
        sys.stdout.flush()
    return success


def check_git_repo():
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def main():
    args = parse_args()

    if not check_git_repo():
        print("Error: not inside a git repository.")
        sys.exit(1)

    if args.count <= 0:
        print("Error: count must be greater than 0.")
        sys.exit(1)

    mode_label = "[DRY RUN] " if args.dry_run else ""
    print(f"{mode_label}Creating {args.count} commits with {args.workers} workers...")
    print()

    start_time = time.time()
    failed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                make_commit,
                i + 1,
                args.count,
                args.prefix,
                args.retries,
                DEFAULT_RETRY_DELAY,
                args.dry_run,
                args.timestamp
            ): i
            for i in range(args.count)
        }
        for future in as_completed(futures):
            if not future.result():
                failed += 1

    elapsed = time.time() - start_time
    print()
    print()
    print(f"Done in {elapsed:.2f}s — {args.count - failed}/{args.count} succeeded, {failed} failed.")

    if args.push and not args.dry_run:
        if failed == 0:
            print("Pushing to remote...")
            push_ok = run_git(["git", "push"], args.retries, DEFAULT_RETRY_DELAY)
            if push_ok:
                print("Push successful.")
            else:
                print("Push failed after retries.")
                sys.exit(1)
        else:
            print("Skipping push due to commit failures.")


if __name__ == "__main__":
    main()
