#!/usr/bin/env python3
"""Project-only lifecycle hook: enqueue metadata, return immediately, drain via ADB."""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('RUX_STATE_DIR',str(ROOT / 'build/chat-hooks'))).resolve()
PROJECT_ROOT = Path(os.environ.get('RUX_PROJECT_ROOT',str(ROOT))).resolve()
EVENTS = {'UserPromptSubmit', 'PermissionRequest', 'PreToolUse', 'PostToolUse', 'Stop', 'Interrupt', 'SessionEnd', 'Failure', 'PermissionCheck', 'NeedsInput'}

def database(directory=DATA):
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / 'queue.sqlite3', timeout=1)
    db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at REAL, session TEXT, turn TEXT, event TEXT, status TEXT DEFAULT "pending", detail TEXT)')
    columns={row[1] for row in db.execute('PRAGMA table_info(events)')}
    for column in ('activity','activity_id'):
        if column not in columns:db.execute('ALTER TABLE events ADD COLUMN '+column+" TEXT DEFAULT ''")
    db.execute('CREATE TABLE IF NOT EXISTS activities (session TEXT PRIMARY KEY, turn TEXT, text TEXT, tool_id TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS sessions (session TEXT PRIMARY KEY, turn TEXT, state TEXT, at REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS thinking_log (at REAL, result TEXT, detail TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS titles (session TEXT PRIMARY KEY, name TEXT, at REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
    db.commit()
    return db

def web_control_active(directory=DATA):
    try:
        return float(json.loads((directory/'web-control.json').read_text()).get('expires',0)) > time.time()
    except (OSError, ValueError, TypeError):
        return False

def sanitized(payload):
    event = payload.get('hook_event_name')
    if event not in EVENTS:
        return None
    cwd = Path(payload.get('cwd') or '').resolve()
    if cwd != PROJECT_ROOT and PROJECT_ROOT not in cwd.parents:
        return None
    session = payload.get('session_id')
    if not isinstance(session, str) or not session or len(session) > 200:
        return None
    turn = payload.get('turn_id') or ''
    if not isinstance(turn, str) or len(turn) > 200:
        return None
    from activity_summary import activity_fields, is_input_request
    # Codex emits this before automatic approval as well as a visible prompt.
    # It cannot establish that the human is actually being asked to intervene.
    if event == 'PermissionRequest':event='PermissionCheck'
    elif event == 'PreToolUse' and is_input_request(payload):event='NeedsInput'
    text,ident=activity_fields(payload) if event in ('PreToolUse','PostToolUse') else ('','')
    return (time.time(), session, turn, event,text,ident)

def transition(current, old_turn, turn, event):
    if event == 'UserPromptSubmit':
        return 'working'
    if old_turn and turn and turn != old_turn:
        return current  # A late stop from an earlier turn must not end the newer one.
    if event in ('PermissionRequest','NeedsInput'):
        return 'attention'
    if event == 'PreToolUse':
        return 'working'
    if event == 'PostToolUse' and current == 'attention':
        return 'working'
    if event == 'Failure':
        return 'failed'
    if event == 'Stop':
        return 'completed'  # Turn ended; does not claim task success.
    if event in ('Interrupt', 'SessionEnd'):
        return 'idle'
    return current

def aggregate(states):
    if 'attention' in states:
        return 'attention'
    if 'working' in states:
        return 'working'
    return states[-1] if states else 'idle'

def enqueue(payload, directory=DATA):
    row = sanitized(payload)
    if row is None:
        return False
    with contextlib.closing(database(directory)) as db:
        db.execute('INSERT INTO events(at,session,turn,event,activity,activity_id) VALUES(?,?,?,?,?,?)', row)
        db.commit()
    return True

def cached_title(db, session, resolver):
    cached = db.execute('SELECT name,at FROM titles WHERE session=?', (session,)).fetchone()
    if cached and time.time() - cached[1] < 15:
        return cached[0]
    try:
        name = resolver(session)
        name = ' '.join(name.split())[:160] if isinstance(name, str) else ''
        if not name and cached:name=cached[0]
    except Exception:
        name = cached[0] if cached else ''
    db.execute('INSERT OR REPLACE INTO titles VALUES(?,?,?)', (session, name, time.time()))
    return name

def worker(directory=DATA, deliver=None, resolve_title=None):
    from rux import command
    live = deliver is None
    if resolve_title is None:
        if deliver is None:
            from codex_metadata import thread_title
            resolve_title = lambda session: thread_title(session.removeprefix("codex:")) if not session.startswith(("claude:","kiro:")) else ""
        else:
            resolve_title = lambda session: ''
    title = ''
    quiet = False
    context = ''
    activity = ''
    if deliver is None:
        from scenario import dispatch
        deliver = lambda state: dispatch(state,title=title,move=not (directory/'motion-disabled').exists(),quiet=quiet,context=context,activity=activity)
    directory.mkdir(parents=True, exist_ok=True)
    # Each enqueue starts a short-lived drainer. Blocking lock avoids the empty-queue
    # handoff race; only one process may send commands to the robot at a time.
    with (directory / 'worker.lock').open('a') as lock, contextlib.closing(database(directory)) as db:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (directory/'disabled').exists() or web_control_active(directory):
            db.execute("UPDATE events SET status='skipped',detail='web control' WHERE status='pending'")
            db.commit()
            return
        adb_path = shutil.which('adb') or str(Path.home() / 'Library/Android/sdk/platform-tools/adb')
        os.environ.setdefault('ADB', adb_path)
        previous = db.execute("SELECT value FROM meta WHERE key='last_display'").fetchone()
        last = previous[0] if previous else None
        while True:
            row = db.execute("SELECT id,at,session,turn,event,activity,activity_id FROM events WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
            if row is None:
                if live:
                    start_heartbeat(directory, db)
                return
            ident, at, session, turn, event, note, tool_id = row
            if time.time() - at > 30:
                db.execute("UPDATE events SET status='expired' WHERE id=?", (ident,))
                db.commit()
                continue
            old = db.execute('SELECT turn,state FROM sessions WHERE session=?', (session,)).fetchone()
            old_turn, current = old if old else ('', 'idle')
            # Prompts received during manual mode were intentionally ignored.
            # The first real tool event after resuming identifies the current turn.
            if last is None and event == 'PreToolUse' and turn:
                old_turn, current = turn, 'working'
            state = transition(current, old_turn, turn, event)
            active_turn = turn if event == 'UserPromptSubmit' or not old_turn else old_turn
            db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)', (session, active_turn, state, at))
            active = db.execute('SELECT session,state FROM sessions WHERE at>? ORDER BY at', (time.time()-900,)).fetchall()
            target = aggregate([r[1] for r in active])
            selected = next((r[0] for r in reversed(active) if r[1] == target), session)
            title = cached_title(db, selected, resolve_title)
            display = json.dumps([target, selected, title], ensure_ascii=False)
            selected_turn = db.execute('SELECT turn FROM sessions WHERE session=?', (selected,)).fetchone()[0]
            parts = [selected, selected_turn, target]
            resume = db.execute("SELECT value FROM meta WHERE key='resume_epoch'").fetchone()
            if resume:parts.append(resume[0])
            context = episode = json.dumps(parts)
            old_episode = db.execute("SELECT value FROM meta WHERE key='thinking_episode'").fetchone()
            episode_changed = not old_episode or old_episode[0] != episode
            if episode_changed:
                db.execute("INSERT OR REPLACE INTO meta VALUES('thinking_episode',?)", (episode,))
                db.execute("INSERT OR REPLACE INTO meta VALUES('thinking_started_at',?)", (str(time.time()),))
            # A stale event from an older turn may update neither state nor motion.
            valid_turn = not old_turn or not turn or turn == old_turn or event == 'UserPromptSubmit'
            if valid_turn:
                if event=='PreToolUse':
                    db.execute('INSERT OR REPLACE INTO activities VALUES(?,?,?,?)',(session,active_turn,note or '',tool_id or ''))
                elif event=='PostToolUse':
                    db.execute('DELETE FROM activities WHERE session=? AND turn=? AND tool_id=?',(session,active_turn,tool_id or ''))
                elif event in ('UserPromptSubmit','Stop','Failure','Interrupt','SessionEnd','PermissionRequest','NeedsInput'):
                    db.execute('DELETE FROM activities WHERE session=?',(session,))
            found=db.execute('SELECT text FROM activities WHERE session=? AND turn=?',(selected,selected_turn)).fetchone()
            activity=found[0] if found and target=='working' else ''
            activity_key=json.dumps([selected,selected_turn,activity],ensure_ascii=False)
            previous_activity=db.execute("SELECT value FROM meta WHERE key='last_activity'").fetchone()
            activity_changed=bool(activity) if previous_activity is None else previous_activity[0]!=activity_key
            old_display = json.loads(last) if last else []
            quiet = target == 'idle' or (old_display and old_display[0] == target) or event == 'PreToolUse'
            db.execute("UPDATE events SET status='sending' WHERE id=?", (ident,))
            db.commit()
            try:
                if display != last or (episode_changed and valid_turn) or activity_changed:
                    deliver(target)
                    last = display
                    db.execute("INSERT OR REPLACE INTO meta VALUES('last_display',?)", (display,))
                    db.execute("INSERT OR REPLACE INTO meta VALUES('last_activity',?)", (activity_key,))
                result, detail = 'delivered', target + ' (device preset)'
            except Exception as exc:
                result, detail = 'failed', type(exc).__name__ + ': ' + str(exc)[:300]
            db.execute('UPDATE events SET status=?,detail=? WHERE id=?', (result, detail, ident))
            db.commit()

def start_heartbeat(directory, db):
    last = db.execute("SELECT value FROM meta WHERE key='last_display'").fetchone()
    if not last or json.loads(last[0])[0] not in ('working','attention','failed'):
        return
    if (directory/'disabled').exists() or (directory/'motion-disabled').exists() or web_control_active(directory):
        return
    with (directory/'worker.log').open('a') as log:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--heartbeat'],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True, close_fds=True)

def heartbeat_tick(directory=DATA, deliver=None, now=None):
    """Renew a lease only. This process never dispatches movements or presets."""
    now = time.time() if now is None else now
    if (directory/'disabled').exists() or (directory/'motion-disabled').exists() or web_control_active(directory):
        return 'stop'
    with (directory/'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'busy'
        with contextlib.closing(database(directory)) as db:
            if db.execute("SELECT 1 FROM events WHERE status IN ('pending','sending') LIMIT 1").fetchone():
                return 'waiting'
            values = dict(db.execute('SELECT key,value FROM meta'))
            display = json.loads(values.get('last_display', '[]'))
            episode = values.get('thinking_episode')
            state = display[0] if display else 'idle'
            if (not display or state not in ('working','attention','failed')
                    or not episode or values.get('thinking_failed_episode') == episode):
                return 'stop'
            session, title = display[1:]
            record = db.execute('SELECT turn,state FROM sessions WHERE session=?', (session,)).fetchone()
            if not record or record[1] != state or json.loads(episode)[:3] != [session,record[0],state]:
                return 'stop'
            prior = float(values.get('last_heartbeat_at','0'))
            if now-prior < 15:return 'waiting'
            db.execute("INSERT OR REPLACE INTO meta VALUES('last_heartbeat_at',?)",(str(now),))
            db.commit()
            try:
                if deliver is None:
                    from rux import command
                    os.environ.setdefault('ADB', shutil.which('adb') or str(Path.home()/'Library/Android/sdk/platform-tools/adb'))
                    from scenario import heartbeat
                    ack=heartbeat(episode)
                    if 'active=false' in ack:return 'stop'
                else:
                    deliver(episode)
                result, detail = 'heartbeat', state + ' lease renewed; no movement sent'
            except Exception as exc:
                result, detail = 'failed', type(exc).__name__ + ': ' + str(exc)[:200]
                db.execute("INSERT OR REPLACE INTO meta VALUES('thinking_failed_episode',?)", (episode,))
            db.execute('INSERT INTO thinking_log VALUES(?,?,?)', (now,result,detail))
            db.commit()
            return result

def heartbeat_loop(directory=DATA):
    # Singleton per project. This process exits on state change, pause, failure,
    # never on a thinking-duration limit. It renews leases, never schedules movement.
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'thinking.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        while True:
            result = heartbeat_tick(directory)
            if result in ('stop','failed'):
                return
            time.sleep(.5)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--heartbeat', '--thinking', dest='heartbeat', action='store_true')
    args = parser.parse_args()
    if args.heartbeat:
        heartbeat_loop()
        return
    if args.worker:
        worker()
        return
    if args.status:
        with contextlib.closing(database()) as db:
            for row in db.execute('SELECT id,event,status,detail FROM events ORDER BY id DESC LIMIT 12'):
                print(json.dumps(row))
            for row in db.execute('SELECT at,result,detail FROM thinking_log ORDER BY at DESC LIMIT 3'):
                print('heartbeat:', json.dumps(row))
        return
    try:
        payload = json.loads(sys.stdin.read(256*1024))
        if (DATA / 'disabled').exists() or web_control_active():
            pass
        elif enqueue(payload):
            with (DATA / 'worker.log').open('a') as log:
                subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker'],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 start_new_session=True, close_fds=True)
    except Exception as exc:
        # Companion issues must not block a prompt, permission request or response.
        print('Rux hook unavailable: ' + type(exc).__name__, file=sys.stderr)
    print('{}', flush=True)

if __name__ == '__main__':
    main()
