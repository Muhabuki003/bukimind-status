#!/usr/bin/env python3
"""
Push a live update to the BUKIMIND virtual office status feed.

Usage (run from ~/bukimind-status/):
  python3 bukimind-update.py --event agent=AUDIT msg="Hello" \
    --agent id=orchestrator status=working task="Building X" \
    output="details" bubble="short"

This updates status.json, commits, and pushes to GitHub live.
"""
import json, os, subprocess, sys, argparse, datetime

REPO = os.path.dirname(os.path.abspath(__file__))


def load():
    with open(f"{REPO}/status.json") as f:
        return json.load(f)


def save(data):
    with open(f"{REPO}/status.json", "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def push(msg):
    subprocess.run(["git", "-C", REPO, "add", "status.json"], check=False)
    r = subprocess.run(["git", "-C", REPO, "diff", "--cached", "--quiet"],
                       capture_output=True)
    if r.returncode == 0:
        return  # nothing changed — don't push empty commits
    subprocess.run(["git", "-C", REPO, "commit", "-m", msg], check=False)
    # HTTPS push to avoid SSH key issues
    subprocess.run(
        ["git", "-C", REPO, "remote", "set-url", "origin",
         "https://github.com/Muhabuki003/bukimind-status.git"], check=False)
    subprocess.run(["git", "-C", REPO, "push", "origin", "main"],
                   capture_output=True, check=False)


def parse_kvs(items):
    """Parse [['key=val', 'key2=val2'], ...] into a dict."""
    d = {}
    for group in items:
        for kv in group:
            if "=" in kv:
                k, v = kv.split("=", 1)
                d[k] = v
    return d


def main():
    parser = argparse.ArgumentParser(
        description="Push live status update to BUKIMIND office")
    parser.add_argument("--event", nargs="*", action="append", default=[],
                        help="--event agent=AUDIT msg=Something")
    parser.add_argument("--agent", nargs="*", action="append", default=[],
                        help="--agent id=orchestrator status=working task=...")
    parser.add_argument("--bar", nargs="*", action="append", default=[],
                        help="--bar loveflix=72 bookistudio=45")
    parser.add_argument("--msg", help="Git commit message (default: auto)")
    args = parser.parse_args()

    data = load()
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    data["updated"] = now
    changes = []

    # Events
    if args.event:
        evt = parse_kvs(args.event)
        data["events"].insert(0, evt)
        data["events"] = data["events"][:6]
        changes.append(f"event:{evt.get('msg','?')[:40]}")

    # Agents
    if args.agent:
        ag = parse_kvs(args.agent)
        aid = ag.pop("id", None)
        if aid:
            for existing in data["agents"]:
                if existing["id"] == aid:
                    existing.update(ag)
                    changes.append(f"agent:{aid}")
                    break

    # Bars
    if args.bar:
        bars = parse_kvs(args.bar)
        data["metrics"]["bars"].update({k: int(v) for k, v in bars.items()})
        changes.append("bars")

    save(data)

    msg = args.msg or ("; ".join(changes) if changes else "status sync")
    push(f"🔄 {msg} [{now}]")
    summary = "; ".join(changes) if changes else "no changes"
    print(f"✅ {summary}")


if __name__ == "__main__":
    main()
