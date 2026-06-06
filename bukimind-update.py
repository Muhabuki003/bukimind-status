#!/usr/bin/env python3
"""
Push a live update to the BUKIMIND virtual office status feed.

Usage (run from ~/bukimind-status/):
  python3 bukimind-update.py --room bookistudio --event agent=AUDIT msg="Hello" \
    --agent id=orchestrator status=working task="Building X" \
    output="details" bubble="short"

  python3 bukimind-update.py --switch-room loveflix
  python3 bukimind-update.py --new-room chronos name="Chronos Trading Bot"
"""
import json, os, subprocess, sys, argparse, datetime, copy

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


DEFAULT_AGENTS = [
    {"id": "orchestrator", "status": "idle", "task": "Standing by",
     "output": "No activity yet"},
    {"id": "agent-2", "status": "idle", "task": "Standing by",
     "output": "No activity yet"},
    {"id": "agent-3", "status": "idle", "task": "Standing by",
     "output": "No activity yet"},
    {"id": "agent-4", "status": "idle", "task": "Standing by",
     "output": "No activity yet"},
    {"id": "agent-5", "status": "idle", "task": "Standing by",
     "output": "No activity yet"},
    {"id": "agent-6", "status": "idle", "task": "Standing by",
     "output": "No activity yet"},
]


def main():
    parser = argparse.ArgumentParser(
        description="Push live status update to BUKIMIND office")
    parser.add_argument("--room", default=None,
                        help="Room to update (default: auto-detect)")
    parser.add_argument("--event", nargs="*", action="append", default=[],
                        help="--event agent=AUDIT msg=Something")
    parser.add_argument("--agent", nargs="*", action="append", default=[],
                        help="--agent id=orchestrator status=working task=...")
    parser.add_argument("--bar", nargs="*", action="append", default=[],
                        help="--bar loveflix=72 bookistudio=45")
    parser.add_argument("--msg", help="Git commit message (default: auto)")
    parser.add_argument("--switch-room",
                        help="Switch the office to show this room")
    parser.add_argument("--new-room",
                        help="Create a new empty room with this id")
    parser.add_argument("--new-room-name",
                        help="Display name for the new room")
    parser.add_argument("--add-agent", nargs="*", action="append", default=[],
                        help="--add-agent id=orchestrator name=Orch role=...")
    parser.add_argument("--delete-room",
                        help="Delete a room by id")
    args = parser.parse_args()

    data = load()
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["updated"] = now

    # Ensure rooms structure exists (migrate from flat)
    if "rooms" not in data:
        flat_agents = data.pop("agents", [])
        flat_metrics = data.pop("metrics", {"tasks": 0, "prs": 0,
                                            "bars": {}})
        data["rooms"] = {
            "hq": {"name": "HQ", "agents": [],
                   "metrics": {"tasks": 0, "prs": 0, "rooms": 1,
                               "bars": {}}},
            "default": {"name": "Main Room", "agents": flat_agents,
                        "metrics": flat_metrics}
        }
        data["current_room"] = "default"

    changes = []

    # --switch-room
    if args.switch_room:
        if args.switch_room in data["rooms"]:
            data["current_room"] = args.switch_room
            changes.append(f"switch:{args.switch_room}")
        else:
            print(f"❌ Room '{args.switch_room}' not found")
            sys.exit(1)

    # --new-room
    if args.new_room:
        rid = args.new_room
        if rid in data["rooms"]:
            print(f"⚠️ Room '{rid}' already exists — skipping")
        else:
            name = args.new_room_name or rid.replace("-", " ").title()
            data["rooms"][rid] = {
                "name": name,
                "agents": copy.deepcopy(DEFAULT_AGENTS),
                "metrics": {"tasks": 0, "prs": 0, "agents": 6,
                            "bars": {}}
            }
            # Add to HQ's children
            hq = data["rooms"].get("hq")
            if hq and "metrics" in hq:
                hq["metrics"]["rooms"] = len([k for k in data["rooms"] if k != "hq"])
            changes.append(f"new-room:{rid}")
            # Also add a bar in the HQ metrics
            if hq and "bars" in hq.get("metrics", {}):
                hq["metrics"]["bars"][rid] = 0

    # --delete-room
    if args.delete_room:
        rid = args.delete_room
        if rid in data["rooms"] and rid != "hq":
            del data["rooms"][rid]
            # Clean up HQ children
            hq = data["rooms"].get("hq", {})
            if "bars" in hq.get("metrics", {}):
                hq["metrics"]["bars"].pop(rid, None)
            if hq and "metrics" in hq:
                hq["metrics"]["rooms"] = len([k for k in data["rooms"] if k != "hq"])
            changes.append(f"delete-room:{rid}")

    # Determine target room for updates
    target_room = args.room
    if not target_room:
        # Auto-detect: if current_room is set and not hq, use it
        target_room = data.get("current_room", "hq")

    def get_target_agents():
        if target_room and target_room in data.get("rooms", {}):
            return data["rooms"][target_room]["agents"]
        # Fallback: flat agents key
        if target_room and target_room == "hq":
            return []
        return data.get("agents", [])

    def get_target_metrics():
        if target_room and target_room in data.get("rooms", {}):
            return data["rooms"][target_room]["metrics"]
        return data.get("metrics", {})

    # Events (always global)
    if args.event:
        evt = parse_kvs(args.event)
        data["events"].insert(0, evt)
        data["events"] = data["events"][:6]
        changes.append(f"event:{evt.get('msg','?')[:40]}")

    # Agents (in target room)
    if args.agent and target_room != "hq":
        agents = get_target_agents()
        ag = parse_kvs(args.agent)
        aid = ag.pop("id", None)
        if aid:
            found = False
            for existing in agents:
                if existing["id"] == aid:
                    existing.update(ag)
                    changes.append(f"agent:{aid}")
                    found = True
                    break
            if not found:
                # Add new agent to room
                entry = {"id": aid}
                entry.update(ag)
                agents.append(entry)
                changes.append(f"agent:{aid} (new)")

    # Bars (in target room's metrics)
    if args.bar:
        metrics = get_target_metrics()
        if "bars" in metrics:
            bars = parse_kvs(args.bar)
            metrics["bars"].update({k: int(v) for k, v in bars.items()})
            changes.append("bars")

    # --add-agent (add to room, similar to --agent but creates if not found)
    if args.add_agent and target_room != "hq":
        agents = get_target_agents()
        ag = parse_kvs(args.add_agent)
        aid = ag.pop("id", None)
        if aid:
            found = False
            for existing in agents:
                if existing["id"] == aid:
                    existing.update(ag)
                    found = True
                    changes.append(f"update:{aid}")
                    break
            if not found:
                entry = {"id": aid}
                entry.update(ag)
                agents.append(entry)
                changes.append(f"add:{aid}")

    # Update agent count in room metrics
    if target_room and target_room in data.get("rooms", {}) and target_room != "hq":
        rdata = data["rooms"][target_room]
        if "metrics" in rdata:
            rdata["metrics"]["agents"] = len(rdata.get("agents", []))

    save(data)

    msg = args.msg or ("; ".join(changes) if changes else "status sync")
    push(f"🔄 {msg} [{now}]")
    summary = "; ".join(changes) if changes else "no changes"
    print(f"✅ {summary}")


if __name__ == "__main__":
    main()
