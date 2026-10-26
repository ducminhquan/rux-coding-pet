"""Small allowlisted tool labels. Never copy descriptions, commands or file contents."""
import hashlib
from pathlib import PurePosixPath
import re
import shlex
import unicodedata

def filename(value):
    if not isinstance(value,str) or not value or len(value)>4096:return ''
    name=PurePosixPath(value.replace('\\','/')).name
    name=''.join(c for c in name if not unicodedata.category(c).startswith('C'))
    return name[:45] if name not in ('.','..') else ''

def summary(payload):
    tool=payload.get('tool_name') or payload.get('toolName') or ''
    if not isinstance(tool,str) or not tool:return ''
    name=tool.rsplit('__',1)[-1].rsplit('.',1)[-1].lower()
    value=payload.get('tool_input') or payload.get('toolInput') or {}
    if isinstance(value,str):
        # MCP inputs sometimes arrive as encoded JSON, never interpret source code.
        import json
        try:value=json.loads(value)
        except ValueError:value={}
    if not isinstance(value,dict):value={}
    path=next((filename(value[k]) for k in ('file_path','filePath','path','file','target_file') if filename(value.get(k))), '')
    if name in ('read','read_file','readfile','fs_read','view_file','read_resource'):
        return 'Đang đọc '+path+'…' if path else 'Đang đọc tệp…'
    if name in ('edit','write','write_file','fs_write','str_replace','multiedit','replace','apply_patch'):
        return 'Đang sửa '+path+'…' if path else 'Đang sửa tệp…'
    if name in ('grep','grep_search','glob','file_search','search','search_code','list_directory','ls'):
        return 'Đang tìm kiếm tệp…'
    if name in ('bash','exec_command','execute_bash','shell','execute_cmd','run_command'):
        raw=value.get('command') or value.get('cmd') or ''
        if isinstance(raw,str) and len(raw)<8192 and not any(s in raw for s in ('\n',';','|','&','`','$','>','<')):
            try:words=shlex.split(raw)
            except ValueError:words=[]
            executable=filename(words[0]).lower() if words else ''
            if executable in ('cat','sed','head','tail','less','more'):
                target=filename(words[-1]) if len(words)>1 and not words[-1].startswith('-') else ''
                return 'Đang đọc '+target+'…' if target else 'Đang đọc tệp…'
            if executable in ('rg','grep','find','ls'):return 'Đang tìm kiếm tệp…'
            if executable in ('pytest','jest','vitest') or (executable in ('npm','pnpm','yarn') and 'test' in words[1:3]):return 'Đang chạy kiểm tra…'
        return 'Đang chạy lệnh…'
    if name in ('web_search','web_run','web_fetch','fetch'):return 'Đang tra cứu…'
    return 'Đang dùng công cụ…'

def is_input_request(payload):
    """Known blocking question tools, never a generic permission preflight."""
    tool=payload.get('tool_name') or payload.get('toolName') or ''
    name=tool.rsplit('__',1)[-1].rsplit('.',1)[-1].lower() if isinstance(tool,str) else ''
    return name in ('request_user_input','askuserquestion')

def activity_fields(payload):
    text=summary(payload)[:80]
    ident=payload.get('tool_use_id') or payload.get('toolUseId')
    if not isinstance(ident,str) or len(ident)>200:
        ident=hashlib.sha256((str(payload.get('tool_name') or payload.get('toolName') or '')+'\0'+text).encode()).hexdigest() if text else ''
    return text,ident
