"""Kiểm tra cú đánh có thật sự vào lỗ không, dựa vào bảng điểm của đài truyền hình.

- Cú bình thường: bi vào lỗ thì cơ thủ được đánh tiếp, mũi tên lượt đánh giữ nguyên.
  Đánh trượt / đánh phòng thủ / phạm lỗi thì mũi tên chuyển sang đối thủ -> loại.
- Cú kết thúc ván: mũi tên có thể đổi (người phá bi ván sau), nên xét điểm số của người đánh có tăng không.

Mẫu mũi tên học từ poster các clip đã có tên cơ thủ trong clips/clips.json (cùng giải đấu).
Toạ độ vùng bảng điểm (khung 1280x720) chỉnh cho đồ hoạ của World Nineball Tour 2023 (US Open, European Open).

usage:
  python turncheck.py ../../scan_out/<trận>/shots.json [...]   # ghi trường 'turn' vào mọi cú trong shots.json
"""
import sys, os, json, subprocess, statistics
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIPS = os.path.join(ROOT, 'clips')
BX, BY, BW, BH = 400, 618, 480, 34          # dải bảng điểm đọc từ video (1280x720), không lấy hàng biểu tượng bi bên dưới
AX, AW = 100, 240                           # cửa sổ mũi tên trong dải (x 500..740)
SL, SR = (110, 160), (322, 372)             # ô điểm số trái / phải trong dải (x 510..560, 722..772)

def strip_frames(video, t0, dur, fps=1.0, box=(BX, BY, BW, BH)):
    x, y, w, h = box
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0, t0):.2f}', '-i', video, '-t', f'{dur:.2f}',
                          '-vf', f'fps={fps},scale=1280:720,crop={w}:{h}:{x}:{y}', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         capture_output=True).stdout
    n = w*h
    return [(max(0, t0)+i/fps, raw[i*n:(i+1)*n]) for i in range(len(raw)//n)]

def poster_strip(jpg):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', jpg, '-vf', f'scale=1280:720,crop={BW}:{BH}:{BX}:{BY}',
                          '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
    return raw if len(raw) == BW*BH else None

def arrow_px(s):
    return [s[y*BW+x] for y in range(BH) for x in range(AX, AX+AW)]

def players_of(video):
    """Tên trái / phải trên bảng điểm = thứ tự trong tiêu đề video "A vs B"."""
    import re
    b = os.path.basename(video).replace('-', ' ')
    m = re.search(r'(?:FINAL\s+)?(.+?) vs (.+?)[ _](?:19|20)\d\d ', b)
    if not m: return None
    left = re.sub(r'^(?:FINAL|SEMI ?FINAL|QUARTER ?FINAL)\s+', '', m.group(1).split('_')[-1].strip(), flags=re.I)
    return left.strip(), m.group(2).strip()

class ArrowModel:
    """Bảng điểm có mũi tên trắng trên nền đỏ ở vị trí cố định (Premier League Pool 2024): đọc trực tiếp, không cần mẫu.
    Toạ độ trong khung 1280x720; dải box, các cửa sổ tính trong dải."""
    box = (520, 600, 240, 40)
    WIN = {'L': (18, 31), 'R': (204, 217)}; REF = {'L': (6, 15), 'R': (222, 230)}; ROWS = (12, 30)
    def __init__(self, left, right): self.mean = {left: None, right: None}; self.side = {'L': left, 'R': right}
    def feat(self, s): return s
    def _m(self, s, x0, x1):
        w = self.box[2]; v = [s[y*w+x] for y in range(*self.ROWS) for x in range(x0, x1)]
        return sum(1 for p in v if p > 200)/len(v), sum(v)/len(v)
    def read(self, s):
        refs = [self._m(s, *self.REF[k])[1] for k in 'LR']
        if not all(70 < r < 150 for r in refs): return None            # không thấy thanh đỏ: bảng điểm bị ẩn
        wl, wr = self._m(s, *self.WIN['L'])[0], self._m(s, *self.WIN['R'])[0]
        if max(wl, wr) < 0.25: return None
        k = 'L' if wl > wr else 'R'
        return self.side[k], abs(wl-wr)*100, 0

class Model:
    box = (BX, BY, BW, BH)
    def feat(self, s): return arrow_px(s)
    """Mẫu mũi tên cho từng cơ thủ của một trận + mặt nạ pixel phân biệt."""
    def __init__(self, samples):
        cls = {}
        for p, v in samples: cls.setdefault(p, []).append(v)
        if len(cls) != 2: raise ValueError(f'cần mẫu của đúng 2 cơ thủ, có {list(cls)}')
        self.mean = {p: [sum(c)/len(vs) for c in zip(*vs)] for p, vs in cls.items()}
        a, b = list(self.mean)
        self.mask = [i for i, (x, y) in enumerate(zip(self.mean[a], self.mean[b])) if abs(x-y) > 60]
        # khoảng cách của chính các mẫu tới mẫu trung bình đúng lớp: dùng làm ngưỡng "có bảng điểm"
        own = [self.dist(v, self.mean[p]) for p, v in samples]
        self.present = statistics.median(own) * 2.5 + 10
    def dist(self, v, m):
        return sum(abs(v[i]-m[i]) for i in self.mask) / len(self.mask)
    def read(self, v):
        """-> (cơ thủ, độ chênh, khoảng cách tốt nhất) hoặc None nếu không thấy bảng điểm."""
        sc = sorted(((self.dist(v, m), p) for p, m in self.mean.items()))
        (d1, p1), (d2, _) = sc
        if d1 > self.present: return None
        return p1, d2-d1, d1

def build_models():
    E = json.load(open(os.path.join(CLIPS, 'clips.json'), encoding='utf-8'))
    by = {}
    for e in E:
        v = (e.get('src') or {}).get('video')
        if not v or not e.get('player') or not e.get('poster'): continue
        s = poster_strip(os.path.join(CLIPS, e['poster']))
        if s: by.setdefault(v, []).append((e['player'], arrow_px(s)))
    return {v: Model(S) for v, S in by.items() if len({p for p, _ in S}) == 2}

def score_changed(a, b, box):
    x0, x1 = box
    d = [abs(a[y*BW+x]-b[y*BW+x]) for y in range(BH) for x in range(x0, x1)]
    return sum(1 for v in d if v > 70) / len(d)

MIN_MARGIN = 25

def next_stroke(sig, t_post, cap=60):
    """Lúc cú đánh kế tiếp bắt đầu: bi cái (đang nằm yên sau cú đánh) rời chỗ ở khung camera trên cao.
    Mũi tên sau cú trượt chỉ đổi sau vài giây, nên phải đọc bảng điểm tới tận lúc này."""
    import math
    ov = [x for x in sig if x['ov'] and t_post <= x['t'] <= t_post+cap]
    W = [(x['t'], [b for b in x['b'] if b[2] == 'white']) for x in ov]
    W = [(t, w[0]) for t, w in W if len(w) == 1]
    d = lambda a, b: math.hypot(a[0]-b[0], a[1]-b[1])
    ref = None
    for k in range(1, len(W)):
        (ta, a), (tb, b) = W[k-1], W[k]
        if ref is None:
            if d(a, b) < 0.8: ref = b          # bi cái đã nằm yên
            continue
        if d(a, ref) > 3 and d(b, ref) > 3: return ta   # rời chỗ ở 2 khung liên tiếp
    return W[-1][0] if ref is not None else t_post+12   # tới khung cuối còn thấy bi cái nằm yên

def load_signals(d):
    import glob
    out = []
    for f in sorted(glob.glob(os.path.join(d, 'signals', '*.jsonl'))):
        out += [json.loads(l) for l in open(f, encoding='utf-8')]
    return out

def check(shot, model, sides, t_end=None):
    """-> dict(verdict='ok'|'reject'|'unknown', reason, shooter, ...)"""
    t0, t1 = shot['t_pre'], shot['t_post']
    t_end = max(t_end or 0, t1+15)        # mũi tên có thể đổi tới ~12 s sau cú trượt
    fr = strip_frames(shot['video'], t0-1, t_end-(t0-1), box=model.box)
    reads = [(t, s, model.read(model.feat(s))) for t, s in fr]
    conf = [(t, r[0]) for t, s, r in reads if r and r[1] >= MIN_MARGIN]
    pre = [p for t, p in conf if t <= t0+0.5]
    if not pre: return {'verdict': 'unknown', 'reason': 'không đọc được bảng điểm trước cú đánh'}
    shooter = max(set(pre), key=pre.count)
    other = [p for p in model.mean if p != shooter][0]
    after = [(t, p) for t, p in conf if t > t0+0.5]
    ending = any('kết thúc ván' in n for n in shot.get('notes', []))
    # Điểm số chỉ dùng để XÁC NHẬN cú thắng ván (ô điểm của người đánh đổi, ô đối thủ không đổi).
    # Không dùng để loại: ô điểm nhiễu (hiệu ứng đồ hoạ) đã làm loại nhầm cú vào lỗ thật.
    side = sides.index(shooter) if sides and shooter in sides else None
    pre_s = [s for t, s, r in reads if t <= t0+0.5 and r]
    post_s = [s for t, s, r in reads if t1 <= t <= t1+12 and r]      # ngay sau cú đánh, chưa sang ván sau
    if isinstance(model, Model) and side is not None and pre_s and post_s:
        mine = max(score_changed(pre_s[-1], p, (SL, SR)[side]) for p in post_s)
        theirs = max(score_changed(pre_s[-1], p, (SL, SR)[1-side]) for p in post_s)
        if mine > 0.04 and theirs < 0.02: return {'verdict': 'ok', 'reason': 'điểm của người đánh tăng (thắng ván)', 'shooter': shooter}
    if ending: return {'verdict': 'unknown', 'reason': 'cú kết thúc ván nhưng điểm số không đổi rõ', 'shooter': shooter}
    # cú bình thường: có ≥2 khung liên tiếp thấy lượt chuyển sang đối thủ -> trượt / phòng thủ
    run = best = 0; flip_t = None
    for t, p in after:
        run = run+1 if p == other else 0
        if run >= 2 and flip_t is None: flip_t = t
    # mũi tên thường đổi 6–12 s sau cú trượt; đổi muộn hơn có thể là do cú kế tiếp (đánh lúc chiếu cận cảnh)
    if flip_t is not None and flip_t > t1+15:
        return {'verdict': 'unknown', 'reason': f'lượt chuyển sang {other} lúc {flip_t:.0f}s, quá muộn để chắc là do cú này', 'shooter': shooter}
    if flip_t is not None: return {'verdict': 'reject', 'reason': f'lượt chuyển sang {other} lúc {flip_t:.0f}s (bi không vào / đánh phòng thủ)', 'shooter': shooter}
    late = [p for t, p in after if t >= t1+1]
    if late.count(shooter) >= 2: return {'verdict': 'ok', 'reason': 'vẫn lượt của người đánh sau cú đánh', 'shooter': shooter}
    return {'verdict': 'unknown', 'reason': 'không đủ khung bảng điểm sau cú đánh', 'shooter': shooter}

def main():
    models = build_models()
    for f in sys.argv[1:]:
        shots = json.load(open(f, encoding='utf-8'))
        sig = load_signals(os.path.dirname(os.path.abspath(f)))
        for s in shots:
            if s.get('manual'): continue                                 # đã soát tay: không ghi đè
            m = models.get(os.path.basename(s['video']))
            if not m and 'Premier League' in s['video'] and players_of(s['video']):
                m = models[os.path.basename(s['video'])] = ArrowModel(*players_of(s['video']))
            if not m: s['turn'] = {'verdict': 'unknown', 'reason': 'chưa có mẫu bảng điểm cho trận này'}; continue
            s['turn'] = check(s, m, players_of(s['video']), next_stroke(sig, s['t_post']) if sig else None)
            print(f"{s['id']}  [{s['confidence']:6}] {s['turn']['verdict']:7} {s['turn'].get('shooter','')}: {s['turn']['reason']}", flush=True)
        json.dump(shots, open(f, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
