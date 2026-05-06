import os
import json
import time
import subprocess
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

GH_USER = os.getenv("GH_USER", "karzinka200888-png")
GH_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = os.getenv("REPO_NAME", "AI_KarinaZamkova_bot")

HEADERS = {
    "Authorization": f"token {GH_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}
BASE_URL = f"https://api.github.com/repos/{GH_USER}/{REPO_NAME}"


def get_file(path):
    r = requests.get(f"{BASE_URL}/contents/{path}", headers=HEADERS, timeout=10)
    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode()
        return json.loads(content), data["sha"]
    return None, None


def put_file(path, content, sha=None):
    encoded = base64.b64encode(
        json.dumps(content, ensure_ascii=False, indent=2).encode()
    ).decode()
    payload = {"message": f"update {path}", "content": encoded}
    if sha:
        payload["sha"] = sha
    r = requests.put(f"{BASE_URL}/contents/{path}", headers=HEADERS, json=payload, timeout=10)
    return r.status_code in (200, 201)


def run_cmd(cmd):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=60
        )
        return (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out"
    except Exception as e:
        return f"ERROR: {e}"


def main():
    print(f"cmdrunner started — watching {GH_USER}/{REPO_NAME}/cmds/pending.json")
    while True:
        try:
            pending, sha = get_file("cmds/pending.json")
            if pending and pending.get("cmd"):
                cmd_id = pending.get("id", "unknown")
                cmd = pending["cmd"]
                print(f"[{cmd_id}] Running: {cmd}")

                output = run_cmd(cmd)
                result = {"id": cmd_id, "cmd": cmd, "output": output, "status": "done"}

                # Write result first, then clear pending
                result_data, result_sha = get_file("cmds/result.json")
                put_file("cmds/result.json", result, result_sha)
                put_file("cmds/pending.json", {"id": "", "cmd": ""}, sha)
                print(f"[{cmd_id}] Done: {output[:120]}")
        except Exception as e:
            print(f"cmdrunner error: {e}")
        time.sleep(10)


if __name__ == "__main__":
    main()
