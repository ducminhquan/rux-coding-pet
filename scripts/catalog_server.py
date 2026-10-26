#!/usr/bin/env python3
"""Loopback-only Rux catalog and bounded ADB preview controller."""
import base64
import contextlib
import fcntl
import hmac
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import threading
import time
import uuid

from chat_hook import DATA, ROOT, database, web_control_active
from rux import command, adb_base

PORT = 8874
ORIGIN = f'http://127.0.0.1:{PORT}'
CATALOG = ROOT/'build/rux-catalog'
TOKEN = secrets.token_urlsafe(32)
STATE_LOCK = threading.Lock()
STATE = {'busy':False, 'job':None, 'result':'ready', 'message':'Chọn một mục để chạy thử.'}
CANCEL = threading.Event()
STARTED = threading.Event()


def validate_preview(body):
    allowed = {'face','motion','motion2','ears','angle','steps','duration_ms','light'}
    if not isinstance(body,dict) or set(body)-allowed:
        raise ValueError('Tham số không hợp lệ')
    spec = dict(face='idle',motion=0,motion2=0,ears=0,angle=20,steps=1,duration_ms=3000,light=-1)
    spec.update(body)
    catalog = json.loads((CATALOG/'catalog.json').read_text())
    faces = set(catalog['native_faces']) | {f['id'] for f in catalog.get('custom_faces',[])}
    if spec['face'] not in faces | {'working','attention','completed','idle','failed'}:
        raise ValueError('Mã mặt không có trong thư viện')
    for key,low,high in [('motion',0,80),('motion2',0,80),('ears',0,3),('angle',1,45),('steps',1,2),('duration_ms',800,4000),('light',-1,8)]:
        if type(spec[key]) is not int or not low <= spec[key] <= high:
            raise ValueError(f'{key}: chỉ nhận {low}–{high}')
    return spec


def validate_voice(body):
    if not isinstance(body,dict) or set(body)!={'voice'} or not isinstance(body['voice'],str):
        raise ValueError('Chọn một giọng trong danh sách')
    voices=json.loads((CATALOG/'catalog.json').read_text()).get('voices',[])
    for voice in voices:
        if voice['id']==body['voice']:
            return {'voice':voice['id'],'asset':voice['asset'],'name':voice['name']}
    raise ValueError('Giọng không có trong thư viện')


def lease():
    DATA.mkdir(parents=True,exist_ok=True)
    temp = DATA/('web-control-'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps({'expires':time.time()+90}))
    temp.replace(DATA/'web-control.json')


def apply_scenario(body):
    """Only mirror locally after the device validates and atomically saves it."""
    from scenario import validate, sync, CONFIG
    config=validate(body)
    with (DATA/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        ack=sync(config)
        temp=CONFIG.with_suffix('.tmp')
        temp.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
        temp.replace(CONFIG)
        (DATA/'scenario-sync.json').write_text(json.dumps({'ack':ack,'at':time.time()}))
        with contextlib.closing(database(DATA)) as db:
            db.execute("DELETE FROM meta WHERE key IN ('last_display','thinking_episode')");db.commit()
    return config


def stop_hardware():
    request=uuid.uuid4().hex
    remote=shlex.join(['am','broadcast','-n','com.rux.assistant/.MainActivity$StopReceiver','--es','request',request])
    subprocess.run(adb_base()+['shell',remote],check=True,stdout=subprocess.DEVNULL,timeout=5)
    until=time.monotonic()+5
    while time.monotonic()<until:
        result=subprocess.run(adb_base()+['logcat','-d','-s','RuxAssistant:I','*:S'],capture_output=True,text=True,check=True,timeout=3)
        if 'OK request='+request in result.stdout:return
        if 'FAILED request='+request in result.stdout:raise RuntimeError('Robot chưa xác nhận dừng')
        time.sleep(.1)
    raise RuntimeError('Hết thời gian chờ xác nhận dừng')


def execute(spec):
    try:
        with (DATA/'worker.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if CANCEL.is_set() or not web_control_active():
                raise RuntimeError('Đã hủy trước khi gửi')
            value=base64.b64encode(json.dumps(spec,ensure_ascii=False).encode()).decode()
            def launched():
                STARTED.set()
                if CANCEL.is_set():stop_hardware()
            if 'voice' in spec:
                command('audio',spec['asset'],title=spec['name'],on_started=STARTED.set)
            else:
                command('preview',value,on_started=launched)
        if 'voice' in spec:
            result='done';message='Rux đã phát xong mẫu '+spec['name']+'.'
        else:
            result='stopped' if CANCEL.is_set() else 'done'
            message='Đã dừng lượt thử.' if CANCEL.is_set() else 'Robot đã xác nhận lượt thử.'
    except Exception as exc:
        result='stopped' if CANCEL.is_set() else 'failed'
        message='Đã yêu cầu dừng.' if CANCEL.is_set() else str(exc)
    finally:
        with STATE_LOCK:
            STATE.update(busy=False,result=result,message=message)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(CATALOG),**kwargs)
    def log_message(self,*args):pass
    def valid_host(self):return self.headers.get('Host')==f'127.0.0.1:{PORT}'
    def reply(self,code,body):
        raw=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)))
        self.end_headers();self.wfile.write(raw)
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        super().end_headers()
    def do_GET(self):
        if not self.valid_host():return self.reply(403,{'error':'Invalid host'})
        if self.path=='/api/status':
            with STATE_LOCK:state=dict(STATE)
            maintenance=(DATA/'web-maintenance').exists()
            if maintenance:state.update(busy=True,result='maintenance',message='Đang cập nhật Rux Assistant… Anh chờ một chút nhé.')
            base=adb_base()
            transport=base[base.index('-s')+1] if '-s' in base else 'USB'
            from scenario import load
            return self.reply(200,dict(state,manual=web_control_active(),token=TOKEN,maintenance=maintenance,transport=transport,applied_scenario=load()))
        if self.path.startswith('/api/'):return self.reply(404,{'error':'Not found'})
        return super().do_GET()
    def do_POST(self):
        if (not self.valid_host() or self.headers.get('Origin')!=ORIGIN
                or not hmac.compare_digest(self.headers.get('X-Rux-Token',''),TOKEN)):
            return self.reply(403,{'error':'Chỉ nhận lệnh từ trang điều khiển trên máy này'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096 or self.headers.get_content_type()!='application/json':raise ValueError('Invalid body')
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict):raise ValueError('Expected object')
        except (ValueError,TypeError):return self.reply(400,{'error':'Dữ liệu không hợp lệ'})
        if self.path=='/api/control':
            if type(body.get('enabled')) is not bool:return self.reply(400,{'error':'enabled must be boolean'})
            if body['enabled']:
                try:
                    with (DATA/'worker.lock').open('a') as lock:
                        fcntl.flock(lock,fcntl.LOCK_EX)
                        command('hold-sessions')
                        lease()
                except Exception as exc:return self.reply(503,{'error':str(exc)})
                with contextlib.closing(database(DATA)) as db:
                    db.execute("DELETE FROM meta WHERE key='last_display'")
                    db.execute("INSERT OR REPLACE INTO meta VALUES('resume_epoch',?)",(uuid.uuid4().hex,))
                    db.commit()
            else:
                with STATE_LOCK:
                    if STATE['busy']:return self.reply(409,{'error':'Hãy dừng lượt thử trước'})
                try:command('release-sessions')
                except Exception as exc:return self.reply(503,{'error':str(exc)})
                (DATA/'web-control.json').unlink(missing_ok=True)
            return self.reply(200,{'manual':body['enabled']})
        if self.path=='/api/heartbeat':
            if web_control_active():lease()
            return self.reply(200,{'manual':web_control_active()})
        if self.path=='/api/scenario':
            if (DATA/'web-maintenance').exists():return self.reply(503,{'error':'Đang cập nhật Rux Assistant'})
            with STATE_LOCK:
                if STATE['busy']:return self.reply(409,{'error':'Hãy dừng lượt thử trước'})
                STATE['busy']=True
            try:
                config=apply_scenario(body)
                return self.reply(200,{'applied_scenario':config,'message':'Đã lưu kịch bản trong Rux. Trạng thái chat tiếp theo sẽ dùng bản này.'})
            except ValueError as exc:return self.reply(400,{'error':str(exc)})
            except Exception as exc:return self.reply(503,{'error':str(exc)})
            finally:
                with STATE_LOCK:STATE['busy']=False
        if self.path=='/api/stop':
            CANCEL.set()
            try:
                with STATE_LOCK:busy=STATE['busy']
                if busy:STARTED.wait(timeout=3)
                stop_hardware()
            except Exception as exc:return self.reply(503,{'error':str(exc)})
            return self.reply(200,{'message':'Đã xác nhận ngắt động cơ chân. Tai có thể hoàn tất nhịp ngắn đã nhận.'})
        if self.path in {'/api/preview','/api/voice-preview'}:
            if (DATA/'web-maintenance').exists():return self.reply(503,{'error':'Đang chuyển kết nối ADB; chưa nhận lượt thử mới'})
            if not web_control_active():return self.reply(409,{'error':'Bật chế độ thử trước'})
            try:spec=validate_voice(body) if self.path=='/api/voice-preview' else validate_preview(body)
            except (ValueError,TypeError) as exc:return self.reply(400,{'error':str(exc)})
            with STATE_LOCK:
                if STATE['busy']:return self.reply(409,{'error':'Rux đang chạy một lượt thử'})
                CANCEL.clear();STARTED.clear();STATE.update(busy=True,job=uuid.uuid4().hex,result='running',message='Đang gửi lệnh tới Rux…')
                job=STATE['job']
            lease();threading.Thread(target=execute,args=(spec,),daemon=True).start()
            return self.reply(202,{'job':job})
        return self.reply(404,{'error':'Not found'})


def main():
    os.environ.setdefault('ADB',adb_base()[0])
    DATA.mkdir(parents=True,exist_ok=True)
    print('Rux control: '+ORIGIN,flush=True)
    server=ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
