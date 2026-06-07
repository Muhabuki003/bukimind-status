#!/usr/bin/env python3
"""BUKIMIND — Push peek data + desk deliveries to the status feed."""
import json, os, subprocess, sys, argparse
from datetime import datetime

REPO = os.path.expanduser("~/bukimind-status")
STATUS = os.path.join(REPO, "status.json")
DESK_ITEMS = os.path.expanduser("~/.hermes/boss-desk/items.jsonl")

def load(): return json.load(open(STATUS))
def save(d):
    json.dump(d, open(STATUS, 'w'), indent=2, ensure_ascii=False)
    open(STATUS, 'a').write('\n')

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

def sync_desk_items(data):
    """Read desk items file and embed in status.json so desk zoom works from Pages."""
    items = []
    if os.path.exists(DESK_ITEMS):
        with open(DESK_ITEMS) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        items.insert(0, json.loads(line))
                    except: pass
    data["desk_items"] = list(reversed(items))
    return data

def find_idle_agent(data, room_id):
    """Find an agent in the room that's idle to deliver papers."""
    room = data.get("rooms", {}).get(room_id)
    if not room: return None
    agents = room.get("agents", [])
    # Prefer idle agents, skip orchestrator (boss)
    for a in agents:
        if a.get("id") != "orchestrator" and a.get("status") in ("idle", "done"):
            return a.get("id")
    # Fallback: any non-orchestrator
    for a in agents:
        if a.get("id") != "orchestrator":
            return a.get("id")
    return agents[0].get("id") if agents else None

def deliver_to_desk(data, room_id, title, file_ext):
    """Trigger a delivery animation: agent walks papers to the boss desk."""
    agent_id = find_idle_agent(data, room_id)
    if not agent_id:
        agent_id = data.get("rooms", {}).get(room_id, {}).get("agents", [{}])[0].get("id", "builder")
    
    now = datetime.utcnow().strftime("%H:%M:%S")
    room = data.get("rooms", {}).get(room_id, {})
    
    # Set delivery trigger
    data["desk_delivery"] = {
        "agent_id": agent_id,
        "room_id": room_id,
        "title": title,
        "ext": file_ext or "doc",
        "ts": now
    }
    
    # Update the delivering agent
    agent, _ = find_agent(data, room_id, agent_id)
    if agent:
        agent["status"] = "working"
        agent["action"] = "Delivering completed work"
        agent["currentFile"] = title[:24]
        agent["snippet"] = f"Walking papers to Boss Desk 📄"
        agent["lastActive"] = now
        recent = agent.get("recentActivity", [])
        recent.append({"ts": now, "desc": f"Delivered {title} to Boss Desk", "file": title})
        agent["recentActivity"] = recent[-50:]
    
    # Add event
    events = data.get("events", [])
    events.insert(0, {"agent": room.get("name", room_id).upper()[:8], "msg": f"📄 {title} delivered to desk"})
    data["events"] = events[:8]
    
    # Sync desk items
    sync_desk_items(data)
    
    data["updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    save(data)
    git(f"deliver: {title} to Boss Desk")
    print(f"✓ {title} delivered to Boss Desk by {agent_id}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--agent","-a", help="Agent ID")
    p.add_argument("--room","-r", help="Room ID", default="bukimind")
    p.add_argument("--action","-ac", help="What they're doing")
    p.add_argument("--file","-f", help="Current file")
    p.add_argument("--code","-c", help="Code snippet")
    p.add_argument("--desc","-d", help="Activity description")
    p.add_argument("--status","-s", help="working/idle/done")
    p.add_argument("--activity","-av", help="working/idle")
    p.add_argument("--deliver","-dl", help="Deliver a file to the Boss Desk (title)")
    p.add_argument("--deliver-ext", help="File extension for delivery")
    p.add_argument("--sync-desk", action="store_true", help="Sync desk items into status (no other changes)")
    args = p.parse_args()

    data = load()

    # Delivery mode
    if args.deliver:
        deliver_to_desk(data, args.room, args.deliver, args.deliver_ext)
        return

    # Sync desk items only
    if args.sync_desk:
        sync_desk_items(data)
        data["updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        save(data)
        git("chore: sync desk items")
        print("✓ Desk items synced to status feed")
        return

    # Normal peek update
    if not args.agent:
        # Just sync desk and update
        sync_desk_items(data)
        data["updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        save(data)
        git("chore: office status update + desk items")
        print("✓ Status + desk items synced")
        return

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

    # Always sync desk items
    sync_desk_items(data)
    
    data["updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    save(data)
    git(f"peek: {args.agent} {args.action or ''} {args.file or ''}")
    print(f"✓ Updated {args.agent}@{args.room}")

if __name__ == "__main__":
    main()
