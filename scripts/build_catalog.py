#!/usr/bin/env python3
"""Build an offline selection catalog from the owner's Rux resource APK."""
import concurrent.futures
import html
import json
from pathlib import Path
import subprocess
import shutil
import zipfile
from cute_svg import render as cute_svg

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/rux-catalog'
NAMES={
1:'Đi tới',2:'Đi lùi',3:'Rẽ trái',4:'Rẽ phải',5:'Đi ngang trái',6:'Đi ngang phải',
7:'Rung chân trái',8:'Rung chân phải',9:'Rung bàn chân trái',10:'Rung bàn chân phải',11:'Nhấc bàn chân trái',12:'Nhấc bàn chân phải',13:'Nghiêng thân trái',14:'Nghiêng thân phải',15:'Giậm chân trái',16:'Giậm chân phải',17:'Nhún thân lên xuống',18:'Lắc thân trái phải',19:'Lắc đầu trái phải',20:'Tư thế nghỉ',21:'Xoay trái tại chỗ khoảng 20°',22:'Xoay phải tại chỗ khoảng 20°',23:'Rung cả hai bàn chân',24:'Rung nhẹ',25:'Xoay nhẹ trái khoảng 5°',26:'Xoay nhẹ phải khoảng 5°',27:'Lắc lư',28:'Lắc đầu',34:'Xoay chân nhẹ',38:'Rung nhẹ chân trái',39:'Rung nhẹ chân phải',43:'Lắc đầu nhẹ',44:'Né trái',45:'Né phải',46:'Né nhẹ trái',47:'Né nhẹ phải',48:'Rung nhanh phía ngoài hai bàn chân',49:'Rung nhanh hai bàn chân',50:'Vặn thân trước sau',51:'Rung nhẹ chân trái',52:'Rung nhẹ chân phải',53:'Xoay bàn chân trái ra ngoài',54:'Xoay bàn chân phải ra ngoài',55:'Xoay trái khoảng 3°',56:'Xoay phải khoảng 3°',57:'Xoay nhẹ bàn chân phải',58:'Né mạnh sang phải',59:'Chà chân trước / giữa / sau',60:'Chà chân trước sau',61:'Động tác nhấc chân khi lơ lửng',62:'Nhấc chân và rung',63:'Đi tới kiểu 2',64:'Đi lùi kiểu 2',65:'Xoay chân trái nhanh',66:'Xoay chân phải nhanh',67:'Rung chân nhanh',68:'Rung nhanh ra ngoài',69:'Bước lên đế kiểu 2',70:'Bước lên đế kiểu 3',71:'Xoay trên đế kiểu 1',72:'Xoay trên đế kiểu 2',73:'Xoay trên đế kiểu 3',74:'Xoay trên đế kiểu 4',75:'Xoay trên đế kiểu 5',76:'Gật đầu',77:'Động tác “Yeah”',78:'Vặn mình nhanh',79:'Lắc thân',80:'Vặn mình theo điệu nhảy'}
for number in [29,30,31,32,33,35,36,37,40,41,42]:NAMES[number]=f'Động tác ngẫu nhiên {number} (hãng không mô tả cụ thể)'
MOVES=[{'code':i,'name':NAMES[i],'verified':i==24} for i in range(1,81)]
EARS=[{'code':'E1','name':'Ra trước n° rồi về vị trí cũ — cmd=1','verified':True},
      {'code':'E2','name':'Ra sau n° rồi về vị trí cũ — cmd=2','verified':True},
      {'code':'E3','name':'Ra trước → ra sau → về vị trí cũ — cmd=3','verified':True}]

def thumbnail(path):
    dest=OUT/'posters'/f'{path.stem}.jpg'
    if dest.exists():return
    for offset in ['0.5','0']:
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',offset,'-i',str(path),'-frames:v','1','-vf','scale=200:200:force_original_aspect_ratio=decrease','-y',str(dest)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if dest.exists() and dest.stat().st_size:return
    raise RuntimeError('Cannot extract thumbnail for '+path.name)

def main():
    for folder in ['videos','posters']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    resource=ROOT/'build/GeeUIResource.apk'
    if resource.exists():
        with zipfile.ZipFile(resource) as archive:
            videos=sorted(n for n in archive.namelist() if n.startswith('assets/video/h') and n.endswith('.mp4'))
            for name in videos:
                target=OUT/'videos'/Path(name).name
                if not target.exists():target.write_bytes(archive.read(name))
    else:
        print('No resource APK: building the custom-face/motion catalog without native video previews.')
    paths=sorted((OUT/'videos').glob('h*.mp4'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(thumbnail,paths))
    cute=json.loads((ROOT/'scripts/cute_faces.json').read_text())
    (OUT/'cute').mkdir(exist_ok=True)
    for face in cute:(OUT/'cute'/f'{face["id"]}.svg').write_text(cute_svg(face))
    voices=json.loads((ROOT/'scripts/voices.json').read_text())
    (OUT/'voices').mkdir(exist_ok=True)
    for voice in voices:shutil.copyfile(ROOT/'android/assets'/voice['asset'],OUT/'voices'/voice['asset'])
    data={'active_scenario':json.loads((ROOT/'scripts/active_scenario.json').read_text()),'voices':voices,'status_faces':json.loads((ROOT/'scripts/status_faces.json').read_text()),'custom_faces':cute,'firmware':'GeeUI 1.2.12162.u','native_faces':[p.stem for p in paths],'motions':MOVES,'ears':EARS}
    (OUT/'catalog.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    template=(ROOT/'scripts/catalog_template.html').read_text()
    (OUT/'index.html').write_text(template.replace('__CATALOG_DATA__',json.dumps(data,ensure_ascii=False)))
    lines=['# Danh mục Rux của anh','',f'Firmware: {data["firmware"]}. Có {len(paths)} clip biểu cảm gốc, xác nhận có tệp trong gói tài nguyên. Chưa chạy thử từng clip.','',
    'Xem ảnh và phát clip trong index.html. Chọn theo mã hNNNN; chưa có nhãn cảm xúc chính thức do bảng Feishu của hãng chưa truy cập được.', '',
    '## Mặt do Rux Assistant tự vẽ','', '| Mã | Biểu cảm |','|---|---|','| working | Mắt xanh dương nhấp nháy / thở nhẹ |','| attention | Mắt vàng chờ anh |','| completed | Mắt cười xanh lá |','| idle | Mắt lim dim |','| failed | Mắt cam báo lỗi |','',
    '## Bộ mặt cute mới', '', '| Mã | Tên |', '|---|---|', *[f'| {f["id"]} | {f["name"]} |' for f in cute], '', '## Chuyển động chân / thân','', 'Tên tiếng Việt dịch từ bảng động tác chính thức; chỉ mã 24 đã được anh xác nhận cử động thật. Các mã còn lại chưa được thử trên máy này.', '', '| Mã | Động tác | Đã thử |','|---|---|---|']
    lines += [f'| {m["code"]} | {m["name"]} | {"Có" if m["verified"] else "Chưa"} |' for m in MOVES]
    lines += ['', '## Tai','', '| Mã chọn | Chức năng |','|---|---|']+[f'| {e["code"]} | {e["name"]} |' for e in EARS]
    lines += ['', 'Tai: chọn số nhịp, khoảng cách giữa nhịp (ms), góc xoay. SDK hiện tại biến góc 0 thành 90°, vì vậy không dùng 0° để yêu cầu đứng yên; dùng lựa chọn Không cử động. Chưa xác minh khả năng điều khiển riêng từng tai. API tai đã có nút thử trên web; chuyển động thực tế vẫn cần anh quan sát xác nhận.', '',
    '## Nguồn','', '- SDK và bảng động tác: https://cn.letianpai.com/?p=5915', '- Bảng tên biểu cảm hãng dẫn tới (chưa truy cập được): https://xmzone.feishu.cn/docx/RqUpd7H4woyoN8xEKfacOCDdnBh', '- Mã nguồn MCU: https://github.com/Letianpai-Robot/GeeUIMcuService', '- Clip: trích từ /vendor/app/GeeUIResource/GeeUIResource.apk của robot, chỉ dùng xem trước cục bộ.', '',
    'Trang có chế độ chạy thử trực tiếp qua máy chủ cục bộ catalog_server.py. Bật chế độ thử để dùng các nút Thử, bấm Dừng chuyển động để hủy. Xuất JSON vẫn chỉ lưu kịch bản.']
    (OUT/'DANH-MUC.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'native_faces':len(paths),'motions':len(MOVES),'ears':len(EARS),'output':str(OUT/'index.html')}))

if __name__=='__main__':main()
