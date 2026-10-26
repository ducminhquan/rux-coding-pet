#!/usr/bin/env python3
"""Temporary Codex CLI -> Rux experiment. No global config or background service."""
import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rux import command

class Reaction:
    def __init__(self, emit):
        self.emit = emit
        self.active = False
        self.terminal = None
        self.robot_errors = 0

    def react(self, state):
        print(f'RUX <- {state}', flush=True)
        try:
            self.emit(state)
        except Exception as exc:
            self.robot_errors += 1
            print(f'RUX delivery failed: {exc}', file=sys.stderr, flush=True)

    def feed(self, event):
        kind = event.get('type')
        if kind == 'turn.started':
            if self.active:
                return
            self.active = True
            self.terminal = None
            self.react('working')
        elif kind in ('turn.completed', 'turn.failed') and self.active and self.terminal is None:
            self.terminal = 'completed' if kind == 'turn.completed' else 'failed'
            self.react(self.terminal)

    def finish(self, returncode):
        # Do not announce success from EOF/exit alone; require a completion event.
        if returncode != 0 or self.terminal is None:
            if self.terminal != 'failed':
                self.terminal = 'failed'
                self.react('failed')
            return 1
        return 1 if self.terminal == 'failed' or self.robot_errors else 0


def run(args):
    emit = (lambda state: None) if args.dry_run else (lambda state: command('state', state))
    reaction = Reaction(emit)
    if args.replay:
        # Replays are labeled explicitly, never represented as a live Codex run.
        print('REPLAY (recorded/synthetic events)', flush=True)
        with open(args.replay) as source:
            for line in source:
                if line.strip():
                    reaction.feed(json.loads(line))
        return reaction.finish(0)

    invocation = ['codex', 'exec', '--json', '--ephemeral', '--sandbox', 'read-only',
                  '--ignore-user-config', '--skip-git-repo-check', '-C', str(ROOT), args.prompt]
    events = queue.Queue()
    started = time.monotonic()
    proc = subprocess.Popen(invocation, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, start_new_session=True)
    def read_stdout():
        try:
            for line in proc.stdout:
                events.put(line)
        finally:
            events.put(None)
    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.log.open('w') as output:
            while True:
                if time.monotonic() - started > args.timeout:
                    raise TimeoutError('Codex trial exceeded timeout')
                try:
                    line = events.get(timeout=.2)
                except queue.Empty:
                    continue
                if line is None:
                    break
                output.write(line)
                output.flush()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                print('CODEX:', event.get('type', 'unknown'), flush=True)
                reaction.feed(event)
        code = proc.wait(timeout=5)
        return reaction.finish(code)
    except (KeyboardInterrupt, TimeoutError) as exc:
        print(str(exc) or 'Interrupted', file=sys.stderr)
        return reaction.finish(1)
    finally:
        if proc.poll() is None:
            import os
            import signal
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
        proc.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prompt', nargs='?', default='Reply with exactly RUX_TRIAL_OK. Do not use tools or change files.')
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='Do not contact the robot')
    parser.add_argument('--log', type=Path, default=ROOT / 'build/codex-trial.jsonl')
    parser.add_argument('--timeout', type=float, default=90)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    return run(args)

if __name__ == '__main__':
    sys.exit(main())
