#!/usr/bin/env python3
"""BUKIMIND — Push peek data to the status feed. Call when working."""
import json, os, subprocess, sys, argparse
from datetime import datetime

REPO = os.path.expanduser("~/bukimind-status")
STATUS = os.path.join(REPO, "status.json")

def load(): return json.load(open(STATUS))
def save(d): json.dump(d, open(STATUS, 'w'), indent=2, ensure_ascii=False); open(STATUS, 'a').write('\n')

def git(msg):
    subprocess.run(["git","add","-A"], cwd=REPO, check=True, capture_output=True)
    r = subprocess.run(["git","commit","-m",msg], cwd=REPO, capture_output=True, text=True)
    if "nothing to commit" in r.stderr: return print("→ No changes")
    r = subprocess.run(["git","push","origin","main"], cwd=REPO, capture_output=True, text=True)
    print("✓ Pushed" if r.returncode==0 else f"✗ {r.stderr[:200]}")

def find_agent(data, rid, aid):
    rooms = data.get("rooms", {})
    r = rooms.get(rid)
    if not r: return None, None
    for a in r.get("agents", []):
        if a.get("id") == aid: return a, r
    return None, None

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--agent","-a", required=True)
    p.add_argument("--room","-r", required=True)
    p.add_argument("--action","-ac", help="What they're doing (e.g. Editing)")
    p.add_argument("--file","-f", help="Current file")
    p.add_argument("--code","-c", help="Code snippet")
    p.add_argument("--desc","-d", help="Activity description (appended to history)")
    p.add_argument("--status","-s", help="working/idle/done")
    p.add_argument("--activity","-av", help="working/idle")
    args = p.parse_args()

    data = load()
    agent, room = find_agent(data, args.room, args.agent)
    if not agent:
        print(f"Agent '{args.agent}' not found in room '{args.room}'")
        sys.exit(1)

    now = datetime.utcnow().strftime("%H:%M:%S")
    if args.action: agent["action"] = args.action
    if args.file: agent["currentFile"] = args.file
    if args.code: agent["snippet"] = args.code
    if args.status: agent["status"] = args.status
    if args.activity: agent["activity"] = args.activity
    agent["lastActive"] = now

    if args.desc:
        recent = agent.get("recentActivity", [])
        recent.append({"ts": now, "desc": args.desc, "file": args.file or ""})
        agent["recentActivity"] = recent[-50:]

    data["updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    save(data)
    git(f"peek: {args.agent} {args.action or ''} {args.file or ''}")
    print(f"✓ Updated {args.agent}@{args.room}")

if __name__ == "__main__":
    main()
