"""Cắt clip cho các cú đã duyệt trong shots.json (do shotscan.py tạo) và thêm vào thư viện clip của app.

usage:
  python cut_shots.py path/to/shots.json --ids ID1,ID2      # cắt đúng các cú này
  python cut_shots.py path/to/shots.json --min-conf high    # cắt mọi cú có độ tin cậy >= high (high|medium|low)
  python cut_shots.py ... --player "Fedor Gorst"            # ghi tên cơ thủ (tool không tự nhận ra người đánh)

clips/clips.json là nguồn dữ liệu; clips/clips.js được sinh lại từ nó (index.html đọc clips.js).
Chạy lại không tạo trùng: clip cùng id sẽ được thay thế."""
import sys, os, json, re, argparse, subprocess
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIPS = os.path.join(ROOT, 'clips')
RANK = {'low': 0, 'medium': 1, 'high': 2}
COLOR_VI = {'yellow': 'vàng', 'blue': 'xanh dương', 'red': 'đỏ', 'purple': 'tím', 'orange': 'cam', 'green': 'xanh lá',
            'maroon': 'nâu đỏ', 'black': 'đen', 'grey': 'xám', 'white': 'trắng'}
POCKET_VI = ['góc gần trái', 'giữa trái', 'góc xa trái', 'góc gần phải', 'giữa phải', 'góc xa phải']

def event_name(video):
    b = os.path.splitext(os.path.basename(video))[0]
    b = re.sub(r'^YTSave\.to_YouTube_Media_[A-Za-z0-9_-]{11}_', '', b)
    b = re.sub(r'_\d{3}_\d{3,4}p$', '', b)
    return b.replace('-', ' ').strip()

def write_js(entries):
    js = ('// SINH TỰ ĐỘNG từ clips.json bởi tools/pool_cv/cut_shots.py — sửa clips.json rồi chạy lại cut_shots.py.\n'
          '// Clip cắt từ video thi đấu có bản quyền: chỉ dùng trên máy, không đưa lên git.\n'
          'window.LOCAL_CLIPS = (window.LOCAL_CLIPS || []).concat(' + json.dumps(entries, ensure_ascii=False, indent=1) + ');\n')
    open(os.path.join(CLIPS, 'clips.js'), 'w', encoding='utf-8').write(js)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('shots')
    ap.add_argument('--ids'); ap.add_argument('--min-conf', choices=list(RANK)); ap.add_argument('--player', default='')
    ap.add_argument('--crf', default='22'); ap.add_argument('--clips-dir', help='mặc định: thư mục clips/ của dự án')
    a = ap.parse_args()
    global CLIPS
    if a.clips_dir: CLIPS = os.path.abspath(a.clips_dir)
    shots = json.load(open(a.shots, encoding='utf-8'))
    if a.ids: want = set(a.ids.split(',')); sel = [s for s in shots if s['id'] in want]
    elif a.min_conf: sel = [s for s in shots if RANK[s['confidence']] >= RANK[a.min_conf]]
    else: raise SystemExit('Chọn --ids hoặc --min-conf')
    if not sel: raise SystemExit('Không có cú nào khớp.')
    os.makedirs(CLIPS, exist_ok=True)
    jf = os.path.join(CLIPS, 'clips.json')
    entries = json.load(open(jf, encoding='utf-8')) if os.path.exists(jf) else []
    for s in sel:
        mp4, jpg = s['id']+'.mp4', s['id']+'.jpg'
        a0, a1 = s['clip']
        print(f"cắt {s['id']}  {a0:.1f}–{a1:.1f}s  θ {s['angle']}°", flush=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{a0:.3f}', '-i', s['video'], '-t', f'{a1-a0:.3f}', '-vf', 'scale=-2:720',
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', a.crf, '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
                        os.path.join(CLIPS, mp4)], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f"{s['t_pre']:.3f}", '-i', s['video'], '-frames:v', '1', '-vf', 'scale=-2:720',
                        '-q:v', '3', os.path.join(CLIPS, jpg)], check=True)
        e = {'id': s['id'], 'file': mp4, 'poster': jpg, 'player': a.player,
             'note': f"{event_name(s['video'])} · bi {COLOR_VI.get(s['ob_color'], s['ob_color'])} vào lỗ {POCKET_VI[s['pocket']]}",
             'angle': s['angle'], 'fps': s['fps'],
             'layout': {'size': 9, 'cb': {'x': s['cb'][0], 'y': s['cb'][1]}, 'ob': {'x': s['ob'][0], 'y': s['ob'][1]}, 'pocket': s['pocket']},
             'src': {'video': os.path.basename(s['video']), 't': s['clip'], 'measured_at': s['t_pre'], 'confidence': s['confidence'], 'auto': True}}
        old = next((x for x in entries if x['id'] == e['id']), None)
        if old and old.get('player') and not a.player: e['player'] = old['player']      # giữ tên đã sửa tay
        entries = [x for x in entries if x['id'] != e['id']] + [e]
    json.dump(entries, open(jf, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    write_js(entries)
    print(f'Xong: {len(sel)} clip. Thư viện có {len(entries)} clip ({jf}).')

if __name__ == '__main__':
    main()
