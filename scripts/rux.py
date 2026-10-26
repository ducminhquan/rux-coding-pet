#!/usr/bin/env python3
"""Control the locally installed Rux Assistant over authorized ADB."""
import argparse
import base64
import json
import time
import uuid
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOUNDS = {"working": "a0125", "completed": "a0040", "attention": "a0126", "failed": "a0059"}

TRANSPORT_FILE = ROOT / 'build/adb-transport.json'

def adb_base():
    base = [os.environ.get('ADB', 'adb')]
    serial = os.environ.get('RUX_SERIAL')
    if not serial and TRANSPORT_FILE.exists():
        try:
            serial = json.loads(TRANSPORT_FILE.read_text())['serial']
        except (OSError, ValueError, KeyError):
            raise RuntimeError('Invalid saved ADB transport; refusing to select another device')
    if serial:
        if not isinstance(serial,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,200}',serial):
            raise RuntimeError('Invalid ADB serial')
        base += ['-s',serial]
    return base

def adb(*args):
    return subprocess.run(adb_base() + list(args), check=True, timeout=12)

def command(name, value="", title="", gesture="", quiet=False, on_started=None, context="", no_motion=False, activity=""):
    request = uuid.uuid4().hex
    # Android 11 restricts a background service opening an Activity. A state
    # change explicitly opens the display via shell; heartbeat never touches it.
    display = name in {'session-state','select-session','set-state','state','play','pose','preview','scenario','audio','motion','face'}
    operation = 'start' if display else 'start-foreground-service'
    component = 'MainActivity' if display else 'ScenarioService'
    remote = ["am", operation, "-n", "com.rux.assistant/."+component,
              "--es", "command", name, "--es", "value", value, "--es", "request", request]
    if activity:
        remote += ["--es", "activity_b64", base64.b64encode(activity[:80].encode("utf-8")).decode("ascii")]
    if context:
        remote += ["--es", "context", context]
    if no_motion:
        remote += ["--ez", "no_motion", "true"]
    if gesture:
        if gesture != "tiny-shake":
            raise ValueError("Unsupported gesture")
        remote += ["--es", "gesture", gesture]
    if quiet:
        remote += ["--ez", "quiet", "true"]
    if title:
        remote += ["--es", "title_b64", base64.b64encode(title[:160].encode("utf-8")).decode("ascii")]
    adb("shell", shlex.join(remote))
    if on_started is not None:
        on_started()
    base = adb_base()
    deadline = time.monotonic() + (30 if name in ("audio", "scenario", "preview") else 8)
    while time.monotonic() < deadline:
        logs = subprocess.run(base + ["logcat", "-d", "-b", "main", "-t", "1000", "-s", "RuxAssistant:I", "*:S"],
                              capture_output=True, text=True, check=True, timeout=5).stdout
        if "FAILED request=" + request in logs:
            raise RuntimeError("Robot SDK rejected request " + request)
        matches = [line for line in logs.splitlines() if "OK request=" + request in line]
        if matches:
            print("Rux acknowledged:", name, flush=True)
            return matches[-1]
        time.sleep(.15)
    raise RuntimeError("No Rux acknowledgment before timeout")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("install", "status", "stop", "motion-stop"):
        sub.add_parser(name)
    for name in ("face", "sound", "say", "audio"):
        child = sub.add_parser(name)
        child.add_argument("value")
    motion = sub.add_parser("motion", help="One explicit vendor micro-shake with motor power-off")
    motion.add_argument("value", choices=["tiny-shake"])
    state = sub.add_parser("state", help="Show pet eyes and play a work-state sound")
    state.add_argument("value", choices=[*SOUNDS, "idle"])
    state.add_argument("--title", default="")
    event = sub.add_parser("event", help="Play a work-state sound; this does not subscribe to Codex")
    event.add_argument("state", choices=SOUNDS)
    args = parser.parse_args()
    try:
        if args.action == "install":
            adb("install", "--no-incremental", "-r", str(ROOT / "build/rux-assistant.apk"))
        elif args.action == "motion":
            # Prevent chat hooks from force-stopping the process during motor cleanup.
            import fcntl
            directory = ROOT / "build/chat-hooks"
            directory.mkdir(parents=True, exist_ok=True)
            disabled = directory / "disabled"
            already_disabled = disabled.exists()
            disabled.touch()
            try:
                with (directory / "worker.lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    try:
                        command("motion", args.value)
                    finally:
                        command("motion-stop")
            finally:
                if not already_disabled:
                    disabled.unlink(missing_ok=True)
        elif args.action == "event":
            command("sound", SOUNDS[args.state])
        else:
            value = getattr(args, "value", "")
            if args.action in ("face", "sound"):
                prefix = "h" if args.action == "face" else "a"
                if not re.fullmatch(prefix + r"\d{4}", value):
                    parser.error("Code must be " + prefix + "NNNN")
            command(args.action, value, title=getattr(args, "title", ""))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, RuntimeError) as exc:
        print(f"ADB failed: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
