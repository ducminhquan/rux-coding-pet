"""Read only a thread's title via the installed Codex App Server protocol."""
import json
import queue
import subprocess
import threading
import time


def thread_title(thread_id, timeout=5):
    proc = subprocess.Popen(['codex', 'app-server', '--stdio'], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    messages = queue.Queue()
    def read():
        for line in proc.stdout:
            try: messages.put(json.loads(line))
            except ValueError: continue
        messages.put(None)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    def request(ident, method, params):
        proc.stdin.write(json.dumps(dict(id=ident, method=method, params=params)) + '\n')
        proc.stdin.flush()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError('Codex metadata read timed out')
            reply = messages.get(timeout=remaining)
            if reply is None: raise RuntimeError('Codex metadata process ended')
            if reply.get('id') == ident:
                if 'error' in reply: raise RuntimeError('Codex metadata unavailable')
                return reply['result']
    try:
        request(1, 'initialize', {'clientInfo': {'name': 'rux_title_reader', 'version': '0.1'}})
        proc.stdin.write('{"method":"initialized"}\n'); proc.stdin.flush()
        result = request(2, 'thread/read', {'threadId': thread_id, 'includeTurns': False})
        name = result.get('thread', {}).get('name')
        return ' '.join(name.split())[:160] if isinstance(name, str) else ''
    finally:
        if proc.poll() is None: proc.terminate()
        try: proc.wait(timeout=1)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=1)
        proc.stdin.close()
        reader.join(timeout=1)
        proc.stdout.close()
