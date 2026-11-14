"""Kiểm tra cú vào lỗ cho giải có bảng điểm KHÔNG có mũi tên lượt đánh (vd WPA 10-Ball 2025).

- Cú kết thúc ván (trên bàn chỉ còn bi cái + 1 bi, tức bi 10): tỉ số ván của một cơ thủ phải tăng ngay sau
  cú đánh (≤ RACK_WIN s). Hàng tỉ số đổi cho biết ai đánh. Đổi muộn hơn: có thể đối thủ mới là người ăn -> unknown.
- Cú giữa ván: so khung full-res trước cú đánh với khung camera trên cao giữa thế bi kế tiếp:
  ok khi số bi giảm đúng 1, còn bi cái, và chỗ cũ của bi mục tiêu trống; reject khi bi mục tiêu vẫn nằm đó.
  Không biết ai đánh (bảng điểm không cho biết lượt).
Bi mục tiêu được phân loại lại màu từ ảnh full-res.

Kết quả ghi vào trường 'turn' {verdict, reason, shooter} của shots.json, giống turncheck.py, nên
cut_shots.py --verified dùng được ngay. Cú có 'manual': true (đã soát bằng hình) không bị ghi đè.

usage:
  python rackcheck.py ../../scan_out/<trận>/shots.json
"""
import sys, os, re, json, math, subprocess
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shotscan as S
import tablefind as tf
from turncheck import load_signals

# vùng tỉ số (khung 1920x1080): x,y,w,h và hai hàng (y tương đối) của hai cơ thủ, theo thứ tự trong tiêu đề "A vs B"
BOARDS = {'wpa 10 ball 2025': {'box': (220, 940, 140, 62), 'rows': [(6, 24), (40, 58)], 'white': 165}}
NAME_FIX = {'Dương Quoc Hoang': 'Dương Quốc Hoàng'}
RACK_WIN = 40          # tỉ số phải đổi trong chừng này giây sau khung trước cú đánh (gồm cả lúc ngắm, đồng hồ 30 s)
DIFF, NOISE = 35, 30   # chữ số đổi thật khác ~50-70 điểm ảnh; nhiễu nền (bảng điểm trong suốt) tới ~25

def board_of(video):
    b = os.path.basename(video).lower()
    return next((v for k, v in BOARDS.items() if k in b), None)

def players(video):
    b = os.path.splitext(os.path.basename(video))[0]
    if ' vs ' not in b: return None
    a, c = b.split(' vs ', 1)
    c = re.sub(r'\s+(last \d+|round of \d+|quarter|semi|final|-).*$', '', c, flags=re.I).strip()
    return [NAME_FIX.get(a.strip(), a.strip()), NAME_FIX.get(c, c)]

def board_frames(video, cfg, t0, dur, fps=1.0):
    x, y, w, h = cfg['box']
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0, t0):.2f}', '-t', f'{dur:.2f}', '-i', video, '-vf',
                          f'fps={fps},scale=1920:1080,crop={w}:{h}:{x}:{y}', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         capture_output=True).stdout
    n = w*h; out = []
    for i in range(len(raw)//n):
        b = raw[i*n:(i+1)*n]
        out.append((max(0, t0)+i/fps, [frozenset(yy*w+xx for yy in range(r0, r1) for xx in range(w) if b[yy*w+xx] > cfg['white'])
                                        for r0, r1 in cfg['rows']]))
    return out

def score_change(video, cfg, t0, t1):
    """(hàng, thời điểm) đầu tiên một hàng tỉ số đổi và giữ nguyên ≥3 khung trong khi hàng kia không đổi; hoặc None."""
    fr = board_frames(video, cfg, t0, t1-t0)
    if len(fr) < 5: return None
    base = fr[0][1]
    for i in range(1, len(fr)-2):
        ds = [[len(fr[i+k][1][r] ^ base[r]) for r in range(2)] for k in range(3)]
        for r in range(2):
            if all(d[r] > DIFF and d[1-r] <= NOISE for d in ds): return r, fr[i][0]
    return None

def post_times(sig, t_post):
    """Vài thời điểm trong đoạn camera trên cao đầu tiên (≥2 mẫu liền nhau) từ t_post."""
    ov = [s['t'] for s in sig if s['ov'] and s['t'] >= t_post-0.01]
    run = ov[:1]
    for t in ov[1:]:
        if t-run[-1] <= 0.6: run.append(t)
        elif len(run) >= 2: break
        else: run = [t]
    return [run[len(run)//2]+0.3, run[-1]-0.2, run[min(1, len(run)-1)]+0.3] if len(run) >= 2 else []

def full_balls(video, cal, t):
    im = S.grab(video, t)
    if not im: return None
    sim = S.grab(video, t, S.SW, S.SH)
    if not S.Scanner(cal['camera']).overhead(sim): return None        # không phải camera trên cao
    return S.detect_full_img(im, cal)

def is_cue(b, s): return min(b['rgb']) > 130 or S._d(b['table'], s['cb']) < 3      # bi cái có thể dính tay / đầu cơ

def moved_before(lay, s, t_end):
    """Có thế bi đứng yên nào (sau cú đánh, trước t_end) mà bi mục tiêu nằm ở chỗ khác không -> bi chưa vào."""
    for L in lay:
        if L['t0'] <= s['t_pre']+0.5 or L['t1'] >= t_end: continue
        oth = [b for b in L['balls'] if b[2] != 'white']
        if len(oth) == 1 and S._d(oth[0], s['ob']) > 2: return L['t0']
        # bi 10 vẫn nằm yên mà bi cái đã dừng ở chỗ khác: trượt / phạm lỗi, đối thủ có thể ăn bi 10 sau đó
        cue = [b for b in L['balls'] if b[2] == 'white']
        if len(oth) == 1 and S._d(oth[0], s['ob']) <= 2 and len(cue) == 1 and S._d(cue[0], s['cb']) > 3: return L['t0']
    return None

def check(s, cal, cfg, names, sig, lay):
    pre = full_balls(s['video'], cal, s['t_pre'])
    if not pre: return {'verdict': 'unknown', 'reason': 'khung trước cú đánh không đọc được'}, None
    obb = min(pre, key=lambda b: S._d(b['table'], s['ob']))
    col = S.color_class(obb['rgb']) if S._d(obb['table'], s['ob']) < 2 else None
    cues = [b for b in pre if is_cue(b, s)]
    if not cues: return {'verdict': 'unknown', 'reason': 'không thấy bi cái ở khung trước'}, col
    stroke = s['stroke'] or s['t_pre']
    if len(pre) == 2:                                                   # bi cái + bi 10: cú kết thúc ván
        ch = score_change(s['video'], cfg, s['t_pre']-2, stroke+RACK_WIN+15)
        if not ch: return {'verdict': 'unknown', 'reason': 'cuối ván: không thấy tỉ số đổi'}, 'blue'
        r, t = ch
        if t < s['t_pre']: return {'verdict': 'unknown', 'reason': 'cuối ván: tỉ số đổi trước cú đánh'}, 'blue'
        mv = moved_before(lay, s, t)
        if mv: return {'verdict': 'reject', 'reason': f'cuối ván: lúc {fmt(mv)} bi 10 chưa vào (thế bi mới) trước khi tỉ số đổi'}, 'blue'
        if t-stroke > RACK_WIN: return {'verdict': 'unknown', 'reason': f'cuối ván: tỉ số {names[r]} đổi muộn ({t-stroke:.0f}s)'}, 'blue'
        return {'verdict': 'ok', 'reason': f'cuối ván: tỉ số {names[r]} tăng sau {t-stroke:.0f}s', 'shooter': names[r]}, 'blue'
    posts = [(tp, full_balls(s['video'], cal, tp)) for tp in post_times(sig, s['t_post'])]
    posts = [(tp, p) for tp, p in posts if p]
    if not posts: return {'verdict': 'unknown', 'reason': 'không có khung trên cao sau cú đánh'}, col
    # khung khớp nhất: bi cái có mặt, số bi gần pre-1 nhất (khung khác có thể bị người che)
    tp, post = min(posts, key=lambda q: (not any(is_cue(b, s) or min(b['rgb']) > 130 for b in q[1]), abs(len(q[1])-(len(pre)-1))))
    if sum(1 for _, p in posts if any(S._d(b['table'], obb['table']) < 1.5 for b in p)) > len(posts)/2:
        return {'verdict': 'reject', 'reason': f'bi mục tiêu vẫn nằm chỗ cũ ({fmt(tp)})'}, col
    if any(S._d(b['table'], obb['table']) < 1.5 for b in post): return {'verdict': 'unknown', 'reason': f'chỗ bi mục tiêu chưa trống ({fmt(tp)})'}, col
    if len(post) != len(pre)-1 or not any(min(b['rgb']) > 130 for b in post):
        return {'verdict': 'unknown', 'reason': f'số bi {len(pre)} -> {len(post)} ({fmt(tp)})'}, col
    if score_change(s['video'], cfg, s['t_pre']-2, tp+1):
        return {'verdict': 'unknown', 'reason': 'tỉ số đổi giữa chừng'}, col
    return {'verdict': 'ok', 'reason': f'giữa ván: {len(pre)} -> {len(post)} bi, chỗ bi mục tiêu trống ({fmt(tp)})'}, col

def fmt(t): return S.fmt(t)

def main():
    for f in sys.argv[1:]:
        shots = json.load(open(f, encoding='utf-8'))
        d = os.path.dirname(os.path.abspath(f))
        cal = json.load(open(os.path.join(d, 'calib.json'), encoding='utf-8')); tf.set_cloth(cal.get('cloth'))
        sig = load_signals(d); lay = S.stable_layouts(sig)
        for s in shots:
            if s.get('manual'): continue                                 # đã soát tay: không ghi đè
            cfg = board_of(s['video']); names = players(s['video'])
            if not cfg or not names: s['turn'] = {'verdict': 'unknown', 'reason': 'chưa có vùng bảng điểm cho trận này'}; continue
            s['turn'], col = check(s, cal, cfg, names, sig, lay)
            if col and col != s['ob_color']: s['turn']['ob_color_scan'] = s['ob_color']; s['ob_color'] = col
            if s['turn']['verdict'] == 'ok' and 'cuối ván' in s['turn']['reason']: s['ball'] = 10      # 10-ball: bi cuối là bi 10
            else: s.pop('ball', None)
            print(f"{s['id']}  [{s['confidence']:6}] {s['turn']['verdict']:7} {s['turn'].get('shooter', ''):18} {s['ob_color']:7} {s['turn']['reason']}", flush=True)
        json.dump(shots, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
