"""Tìm các cú đưa bi vào lỗ trong video thi đấu quay bằng camera trên cao ở đầu bàn.

usage:
  python shotscan.py VIDEO [--out DIR] [--fps 2] [--stage calib|scan|events|all]

Kết quả trong DIR/<tên video>/ :
  calib.json      camera đã hiệu chỉnh (trung vị các đường mép bàn trên nhiều khung sạch)
  signals/*.jsonl tín hiệu từng khung (camera trên cao? vị trí bi thô) - lưu đệm theo đoạn 10 phút
  shots.json      các cú đã đo chính xác (thế bi, lỗ, θ, độ tin cậy, khung giờ cắt clip)
  report.html     trang duyệt: ảnh trước/sau cú đánh có đánh dấu bi
Cắt clip cho các cú đã duyệt bằng cut_shots.py."""
import sys, os, json, math, subprocess, argparse, time, statistics
try: sys.stdout.reconfigure(encoding='utf-8')
except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppm import Img
from camera import ray_plane, project
import tablefind as tf
from balls import detect as detect_full, refine
from geom import theta as geom_theta, pockets as aim_points

R = 1.125
SW, SH, F = 640, 360, 3            # khung quét nhanh = 1920x1080 / 3
POCKETS = [(0, 0), (50, 0), (100, 0), (0, 50), (50, 50), (100, 50)]
VIEW = 'end'        # 'top': camera nhìn thẳng từ trên xuống (trường 'view' của file hiệu chỉnh)
NW_SCAN, NW_FULL = 0.07, 0.08   # bi sọc quay phần trắng lên trông như bi cái: tỉ lệ điểm ảnh không trắng trong đĩa 0.9r lớn hơn

def set_view(cal):
    global VIEW
    VIEW = cal.get('view', 'end'); tf.set_cloth(cal.get('cloth'))

def non_white(im, cx, cy, r):
    """Tỉ lệ điểm ảnh không trắng trong đĩa 0.9r: bi cái ~0.02 (vài chấm), bi sọc (kể cả khi phần trắng quay lên) >= 0.1."""
    rr = 0.9*r; ri = int(rr)+1; tot = nw = 0
    for dy in range(-ri, ri+1):
        for dx in range(-ri, ri+1):
            x, y = int(cx)+dx, int(cy)+dy
            if (x+0.5-cx)**2+(y+0.5-cy)**2 > rr*rr or not (0 <= x < im.w and 0 <= y < im.h): continue
            c = im.get(x, y); tot += 1
            if min(c) < 150 or max(c)-min(c) > 70: nw += 1
    return nw/tot if tot else 1.0

def plain_white(b):
    """Bi trắng có thể là bi cái: với camera trên cao loại bi sọc (b['nw'] từ balls.detect)."""
    return min(b['rgb']) > 130 and (VIEW != 'top' or b.get('nw', 0) < NW_FULL)

# ------------------------------------------------------------------ ffmpeg
def probe(video):
    o = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate:format=duration',
                        '-of', 'json', video], capture_output=True, text=True, check=True)
    j = json.loads(o.stdout); n, d = j['streams'][0]['r_frame_rate'].split('/')
    return float(j['format']['duration']), float(n)/float(d)

def grab(video, t, w=1920, h=1080):
    """Một khung RGB tại thời điểm t (giây)."""
    vf = ['-vf', f'scale={w}:{h}']          # luôn co giãn: có video không đúng 1080 dòng (vd 1920x1068)
    o = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{max(0, t):.3f}', '-i', video, '-frames:v', '1', *vf,
                        '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True)
    if len(o.stdout) < w*h*3: return None
    return Img.from_raw(w, h, o.stdout[:w*h*3])

def frames(video, start, dur, fps):
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-ss', f'{start:.3f}', '-t', f'{dur:.3f}', '-i', video, '-an', '-sn',
                          '-vf', f'fps={fps},scale={SW}:{SH}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         stdout=subprocess.PIPE)
    n = SW*SH*3; i = 0
    while True:
        b = p.stdout.read(n)
        if len(b) < n: break
        yield start + i/fps, Img.from_raw(SW, SH, b); i += 1
    p.wait()

# ------------------------------------------------------------------ 1. hiệu chỉnh
def calibrate_video(video, dur, n=40):
    n = max(8, min(n, int(dur/30)))
    rows = []
    for i in range(n):
        t = dur*(0.02 + 0.96*i/(n-1))
        im = grab(video, t)
        if not im: continue
        q = tf.find_quad(im)
        if not tf.plausible_end_view(q): continue
        L = tf.detect_lines(im, q)
        if L: rows.append((t, L))
        print(f'  calib {i+1}/{n}  t={t:7.1f}s  {"OK" if L else "-"}', flush=True)
    if not rows: raise SystemExit('Không tìm thấy khung camera trên cao nào đủ sạch để hiệu chỉnh.')
    key = lambda L: (L['L']['a']*600+L['L']['b'], L['R']['a']*600+L['R']['b'], L['T']['a']*960+L['T']['b'])
    # nhóm khung có cùng khung hình (camera cố định) - lấy nhóm lớn nhất
    best = []
    for _, L0 in rows:
        k0 = key(L0); grp = [r for r in rows if all(abs(a-b) < 4 for a, b in zip(key(r[1]), k0))]
        if len(grp) > len(best): best = grp
    med = {}
    for k in ('L', 'R', 'T', 'FS', 'N'):
        if any(k not in r[1] for r in best): continue           # FS có thể vắng (bàn nỉ màu)
        med[k] = {'form': best[0][1][k]['form'], 'a': statistics.median(r[1][k]['a'] for r in best),
                  'b': statistics.median(r[1][k]['b'] for r in best)}
    cam, rms = tf.fit_camera(med)
    return {'camera': cam, 'camera_param_names': ['X', 'Y', 'Z', 'yaw', 'pitch', 'roll', 'f_px'], 'fit_rms_px': rms,
            'image_lines': med, 'frames_used': [round(r[0], 1) for r in best], 'frames_tried': n, 'image_size': [1920, 1080]}

# ------------------------------------------------------------------ 2. quét nhanh
class Scanner:
    def __init__(s, cam, rail_ref=None):
        s.cam = cam; s.rail_ref = rail_ref     # màu băng học từ khung hiệu chỉnh (bàn băng sáng); None -> băng tối
        sp = lambda P: tuple(v/F for v in project(cam, P)[0])
        s.bed_pts = [tuple(map(int, sp((x, y, 0)))) for x in range(8, 95, 7) for y in range(5, 46, 5)]
        s.rail_pts = [tuple(map(int, sp((x, y, -2.0)))) for x in range(10, 91, 8) for y in (-3.5, 53.5)]
        cs = [sp(t) for t in ((0, 0, -R), (100, 0, -R), (0, 50, -R), (100, 50, -R))]
        s.x0 = max(0, int(min(c[0] for c in cs))); s.x1 = min(SW-1, int(max(c[0] for c in cs))+1)
        s.y0 = max(0, int(min(c[1] for c in cs))); s.y1 = min(SH-1, int(max(c[1] for c in cs))+1)
        s.w = s.x1-s.x0
        s.inbed = bytearray(s.w*(s.y1-s.y0))
        s.tab = {}
        for y in range(s.y0, s.y1):
            for x in range(s.x0, s.x1):
                u, v = ray_plane(cam, ((x+.5)*F, (y+.5)*F), -R)
                if 0.6 <= u <= 99.4 and 0.6 <= v <= 49.4: s.inbed[(y-s.y0)*s.w+(x-s.x0)] = 1
        # bán kính bi dự kiến (px nhỏ) theo hàng ảnh
        s.rad = {}
        for y in range(s.y0, s.y1):
            u, v = ray_plane(cam, (960, (y+.5)*F), -R); _, zc = project(cam, (u, v, -R)); s.rad[y] = cam[6]*R/zc/F

    def overhead(s, im):
        cl = [im.get(*p) for p in s.bed_pts if 0 <= p[0] < SW and 0 <= p[1] < SH]
        ok = [c for c in cl if tf.is_cloth(c)]
        if s.rail_ref:
            rail = [(im.get(*p), r) for p, r in zip(s.rail_pts, s.rail_ref) if r and 0 <= p[0] < SW and 0 <= p[1] < SH]
            good = sum(1 for c, r in rail if sum(abs(c[i]-r[i]) for i in range(3)) < 60)
            if len(ok) < 0.55*len(cl) or good < 0.6*len(rail): return None
        else:
            rail = [im.get(*p) for p in s.rail_pts if 0 <= p[0] < SW and 0 <= p[1] < SH]
            dark = sum(1 for c in rail if sum(c) < 300)
            if len(ok) < 0.55*len(cl) or dark < 0.6*len(rail): return None
        return tuple(statistics.median(c[i] for c in ok) for i in range(3))

    def balls(s, im, ref, TH=40, k=2):
        w, h = s.w, s.y1-s.y0
        m = bytearray(w*h)
        for yy in range(h):
            y = yy+s.y0; row = yy*w; rr = ref
            if tf.CLOTH:                       # nỉ màu: độ sáng đổi theo chiều sâu -> màu nền riêng từng hàng
                cs = [im.get(xx+s.x0, y) for xx in range(0, w, 5) if s.inbed[row+xx]]
                if len(cs) >= 9: rr = tuple(sorted(c[i] for c in cs)[len(cs)//2] for i in range(3))
            for xx in range(w):
                if s.inbed[row+xx]:
                    c = im.get(xx+s.x0, y)
                    if abs(c[0]-rr[0])+abs(c[1]-rr[1])+abs(c[2]-rr[2]) > TH: m[row+xx] = 1
        # co (erosion) bằng cửa sổ vuông (2k+1): bỏ cây cơ, mép bóng
        e = bytearray(w*h); W2 = 2*k+1
        tmp = bytearray(w*h)
        for yy in range(h):
            row = yy*w; run = 0
            for xx in range(w):
                run = run+1 if m[row+xx] else 0
                if run >= W2: tmp[row+xx-k] = 1
        for xx in range(w):
            run = 0
            for yy in range(h):
                run = run+1 if tmp[yy*w+xx] else 0
                if run >= W2: e[(yy-k)*w+xx] = 1
        seen = bytearray(w*h); out = []
        for i in range(w*h):
            if not e[i] or seen[i]: continue
            st = [i]; seen[i] = 1; comp = []
            while st:
                j = st.pop(); comp.append(j); x = j % w
                for nb in ((j-1) if x else -1, (j+1) if x < w-1 else -1, j-w, j+w):
                    if 0 <= nb < w*h and e[nb] and not seen[nb]: seen[nb] = 1; st.append(nb)
            cy = sum(j//w for j in comp)/len(comp)+s.y0; cx = sum(j % w for j in comp)/len(comp)+s.x0
            r = s.rad.get(int(cy), 6.5); core = math.pi*max(1.0, r-k-0.5)**2
            if not 0.25*core <= len(comp) <= 3.2*core: continue
            xs = [j % w for j in comp]; ys = [j//w for j in comp]
            if max(xs)-min(xs) > 2.6*r or max(ys)-min(ys) > 2.6*r: continue
            if VIEW != 'top': cy -= 0.3*r                      # camera đầu bàn: lõi bị bóng đổ kéo xuống dưới
            ri = int(r)+1
            disk = [im.get(int(cx)+dx, int(cy)+dy) for dx in range(-ri, ri+1) for dy in range(-ri, ri+1)
                    if dx*dx+dy*dy <= r*r and 0 <= int(cx)+dx < SW and 0 <= int(cy)+dy < SH]
            disk = [c for c in disk if abs(c[0]-ref[0])+abs(c[1]-ref[1])+abs(c[2]-ref[2]) > TH] or disk
            whitish = sum(1 for c in disk if min(c) > 150 and max(c)-min(c) < 70)/len(disk)
            chrom = [c for c in disk if max(c)-min(c) > 25]
            if len(chrom) >= 0.3*len(disk): rgb = tuple(statistics.median(c[q] for c in chrom) for q in range(3))
            else: rgb = tuple(statistics.median(c[q] for c in disk) for q in range(3))
            u, v = ray_plane(s.cam, (cx*F+1, cy*F+1), -R)
            lab = 'white' if whitish >= 0.2 else color_class(rgb)
            if lab == 'white' and VIEW == 'top' and non_white(im, cx+0.5, cy+0.5, r) >= NW_SCAN:  # bi sọc quay phần trắng lên
                lab = color_class(tuple(statistics.median(c[q] for c in chrom) for q in range(3))) if chrom else 'stripe'
                if lab in ('white', 'grey'): lab = 'stripe'
            out.append([round(u, 2), round(v, 2), lab, [round(cx*F), round(cy*F)]])
        return out

def color_class(c):
    r, g, b = c; mx, mn = max(c), min(c); l = (r+g+b)/3
    if mn > 140 and mx-mn < 70: return 'white'
    if mx-mn <= 25: return 'black' if l < 75 else 'grey'
    if tf.CLOTH and mx == b and g >= r-10 and l < 90: return 'black'     # nỉ xanh dương: bi đen bị ám xanh
    # hue
    if mx == r: hue = (60*((g-b)/(mx-mn))) % 360
    elif mx == g: hue = 60*((b-r)/(mx-mn))+120
    else: hue = 60*((r-g)/(mx-mn))+240
    if hue < 15 or hue >= 330: return 'maroon' if l < 95 else 'red'
    if hue < 40: return 'maroon' if l < 90 else 'orange'
    if hue < 70: return 'yellow'
    if hue < (190 if tf.CLOTH else 170): return 'green'                     # nỉ xanh dương kéo bi xanh lá về phía lam
    if hue < 255: return 'blue'
    return 'purple'

def learn_rail(video, cal):
    """Bàn có băng sáng (vd Premier League): kiểm tra 'băng tối' không phân biệt được camera đầu bàn với camera
    nhìn thẳng từ trên xuống. Khi đó học màu từng điểm trên băng từ các khung đã dùng để hiệu chỉnh."""
    sc = Scanner(cal['camera']); ims = [grab(video, t, SW, SH) for t in cal.get('frames_used', [])[:8]]
    ims = [im for im in ims if im]
    if not ims: return None
    dark = statistics.median(sum(1 for p in sc.rail_pts if 0 <= p[0] < SW and 0 <= p[1] < SH and sum(im.get(*p)) < 300)/len(sc.rail_pts) for im in ims)
    if dark >= 0.6: return None                                     # băng tối: cách cũ dùng tốt
    ref = []
    for p in sc.rail_pts:
        if not (0 <= p[0] < SW and 0 <= p[1] < SH): ref.append(None); continue
        cs = [im.get(*p) for im in ims]; ref.append([statistics.median(c[i] for c in cs) for i in range(3)])
    return ref

def scan(video, dur, cam, outdir, fps, chunk=600, rail_ref=None):
    sc = Scanner(cam, rail_ref); sd = os.path.join(outdir, 'signals'); os.makedirs(sd, exist_ok=True)
    meta = os.path.join(sd, 'meta.json'); want = {'camera': [round(v, 4) for v in cam], 'fps': fps}
    if rail_ref: want['rail'] = True                                 # chỉ thêm khi có: không làm mất bộ đệm cũ
    if not os.path.exists(meta) or json.load(open(meta)) != want:      # đổi camera / fps -> quét lại
        for fn in os.listdir(sd): os.remove(os.path.join(sd, fn))
        json.dump(want, open(meta, 'w'))
    nchunks = math.ceil(dur/chunk); t_start = time.time()
    for ci in range(nchunks):
        fn = os.path.join(outdir, 'signals', f'{ci:04d}.jsonl')
        if os.path.exists(fn): continue
        rows = []
        for t, im in frames(video, ci*chunk, min(chunk, dur-ci*chunk), fps):
            ref = sc.overhead(im)
            rows.append({'t': round(t, 2), 'ov': 1 if ref else 0, 'b': sc.balls(im, ref) if ref else []})
        with open(fn+'.tmp', 'w') as f:
            for r in rows: f.write(json.dumps(r)+'\n')
        os.replace(fn+'.tmp', fn)
        el = time.time()-t_start
        print(f'  scan {ci+1}/{nchunks}  ({min(dur,(ci+1)*chunk)/60:.0f}/{dur/60:.0f} phút video, {el/60:.1f} phút)', flush=True)
    sig = []
    for ci in range(nchunks):
        with open(os.path.join(outdir, 'signals', f'{ci:04d}.jsonl')) as f: sig += [json.loads(l) for l in f]
    return sig

# ------------------------------------------------------------------ 3. sự kiện
def _d(a, b): return math.hypot(a[0]-b[0], a[1]-b[1])
def _ang(u, v):
    c = (u[0]*v[0]+u[1]*v[1])/((math.hypot(*u)*math.hypot(*v)) or 1); return math.degrees(math.acos(max(-1, min(1, c))))

WHITE_TOL = 2.5   # vị trí bi cái ở bản quét thô dao động nhiều hơn (bóng đổ, đầu cơ)

def match(A, B, tol):
    """Ghép bi theo vị trí (tham lam theo khoảng cách). Bi trắng chỉ ghép với bi trắng, dung sai WHITE_TOL.
    Trả về pairs, unmatched_A, unmatched_B (chỉ số)."""
    W = ('white', 'grey')            # bi cái chạm đầu cơ / đang lăn có thể ra 'grey'
    def ok(a, b):
        if (a[2] == 'white') != (b[2] == 'white') and not (a[2] in W and b[2] in W):
            return _d(a, b) <= 1.0         # bi cái bị ám màu (chạm đầu cơ, bóng tay) vẫn ghép nếu đúng chỗ
        return _d(a, b) <= (WHITE_TOL if 'white' in (a[2], b[2]) else tol)
    cand = sorted((_d(a, b), i, j) for i, a in enumerate(A) for j, b in enumerate(B) if ok(a, b))
    ua, ub, pairs = set(range(len(A))), set(range(len(B))), []
    for d, i, j in cand:
        if i in ua and j in ub: pairs.append((i, j)); ua.discard(i); ub.discard(j)
    return pairs, ua, ub

def same_layout(A, B, tol=1.0):
    p, ua, ub = match(A, B, tol); return not ua and not ub

def persistent(sig, tol=1.2, dt=1.1):
    """Chỉ giữ bi có mặt ở khung camera trên cao liền trước hoặc liền sau (loại đốm chập chờn)."""
    ov = [s for s in sig if s['ov']]; out = []
    for i, s in enumerate(ov):
        nb = [ov[j] for j in (i-1, i+1) if 0 <= j < len(ov) and abs(ov[j]['t']-s['t']) <= dt]
        keep = [b for b in s['b'] if any(_d(b, c) <= (WHITE_TOL if b[2] == 'white' else tol) for n in nb for c in n['b'])]
        out.append({'t': s['t'], 'ov': 1, 'b': keep})
    return out

def _vote(cur):
    """Bi đại diện của một cửa sổ đứng yên: vị trí trung vị + màu chiếm đa số."""
    ref = cur[len(cur)//2]['b']; out = []
    for b in ref:
        xs, ys, cls = [], [], []
        for s in cur:
            near = [c for c in s['b'] if _d(c, b) <= (WHITE_TOL if b[2] in ('white', 'grey') else 1.2)]
            if near:
                c = min(near, key=lambda c: _d(c, b)); xs.append(c[0]); ys.append(c[1]); cls.append(c[2])
        col = max(set(cls), key=cls.count) if cls else b[2]
        if cls.count('white') >= max(1, len(cls)/3): col = 'white'
        out.append([round(statistics.median(xs), 2), round(statistics.median(ys), 2), col, b[3]])
    return out

def stable_layouts(sig, min_n=2, tol=0.9, max_gap=1.6):
    ov = persistent(sig)
    raw = []; cur = []
    def flush():
        if len(cur) >= min_n and cur[0]['b']:
            raw.append({'t0': cur[0]['t'], 't1': cur[-1]['t'], 'n': len(cur), 'balls': _vote(cur), 'ts': [c['t'] for c in cur]})
    for s in ov:
        if cur and (s['t']-cur[-1]['t'] <= max_gap) and same_layout(cur[0]['b'], s['b'], tol): cur.append(s); continue
        flush(); cur = [s]
    flush()
    def absorb(P, L, balls=None):
        if balls is not None: P['balls'] = balls
        P['t1'] = L['t1']; P['n'] += L['n']; P['ts'] = P['ts']+L['ts']
    merged = []
    for k, L in enumerate(raw):
        if merged:
            P = merged[-1]; p, ua, ub = match(P['balls'], L['balls'], 1.2)
            if not ua and not ub: absorb(P, L); continue                         # giống hệt (camera cắt đi rồi quay lại)
            if not ua and ub and L['t0']-P['t1'] < 20:                             # L thấy thêm bi: P bị che một phần
                has_w = any(b[2] == 'white' for b in P['balls'])
                extra = [L['balls'][j] for j in ub if not (has_w and L['balls'][j][2] == 'white')]
                absorb(P, L, P['balls']+extra); continue
            if ua and not ub and L['t0']-P['t1'] < 4 and k+1 < len(raw):         # L thiếu bi: bị tay/cơ che?
                N = raw[k+1]; miss = [P['balls'][i] for i in ua]
                if all(match([m], N['balls'], 1.2)[0] for m in miss):           # bi thiếu xuất hiện lại ở thế sau
                    absorb(P, L); continue
        merged.append({**L, 'ts': list(L['ts'])})
    return merged

def cue(b):
    w = [x for x in b if x[2] == 'white']
    return w[0] if len(w) == 1 else None

def find_events(sig, layouts):
    ev = []; hist = []
    ov = [s for s in sig if s['ov']]
    others = lambda L: [x for x in L['balls'] if x[2] != 'white']
    i = 0
    while i+1 < len(layouts):
        A, B = layouts[i], layouts[i+1]
        if any(same_layout(H['balls'], B['balls'], 1.0) for H in hist[-12:]):        # phát lại cảnh cũ
            layouts.pop(i+1); continue
        hist.append(A); i += 1
        oa, ob = others(A), others(B); ca, cb = cue(A['balls']), cue(B['balls'])
        if not ca: continue
        if len(ob) > len(oa):                                                     # ván mới
            if len(oa) != 1: continue
            potted = [oa[0]]; note = 'cú kết thúc ván'
        else:
            p, ua, ub = match(oa, ob, 1.5)
            for ia in sorted(ua):                                                 # bi bị đẩy đi: ghép cùng màu
                cand = [jb for jb in ub if ob[jb][2] == oa[ia][2] and _d(oa[ia], ob[jb]) < 40]
                if cand:
                    jb = min(cand, key=lambda j: _d(oa[ia], ob[j])); p.append((ia, jb)); ub.discard(jb)
            paired = {a for a, _ in p}
            potted = [oa[k] for k in range(len(oa)) if k not in paired]; note = ''
            moved_cue = cb is None or _d(ca, cb) > WHITE_TOL
            if not potted or not moved_cue: continue
        if len(potted) != 1: continue
        obb = potted[0]
        t_end = min(B['t0'], A['t1']+6) if note else min(B['t1'], B['t0']+4, A['t1']+20)          # ván mới: không theo dõi sang ván sau
        mids = [s for s in ov if A['t1'] < s['t'] < t_end]
        statics = [x for x in A['balls'] if x is not obb and x is not ca]
        last, tlast, stroke, still_t, dir0, npts = obb, None, None, A['t1'], None, 0
        for s in mids:
            c2 = cue(s['b'])
            # người đứng che bàn -> đốm lạ (áo, tay) dễ bị nhận là bi đang lăn: bỏ khung thiếu nhiều bi đứng yên
            seen = sum(1 for st in statics if any(_d(x, st) < 1.5 for x in s['b']))
            occluded = statics and seen < 0.75*len(statics)
            if c2 and _d(c2, ca) <= WHITE_TOL: still_t = s['t']          # bi cái vẫn nằm yên ở khung này
            # lúc đánh = khung đầu tiên thấy bi cái rời chỗ, với khung trước đó (≤0.75 s) còn thấy nó nằm yên
            if stroke is None and c2 and _d(c2, ca) > WHITE_TOL and s['t']-still_t <= 1.1: stroke = s['t']
            # bi mục tiêu đang lăn: màu có thể nhoè -> nhận mọi đốm không phải bi cái / bi đứng yên khác,
            # nhưng phải đi thẳng theo hướng ban đầu và ngày càng xa chỗ cũ
            cands = []
            for x in s['b']:
                if x[2] == 'white' or (c2 and _d(x, c2) < 2) or any(_d(x, st) < 1.5 for st in statics): continue
                # bi khác bị bi cái chạm nhẹ, xê dịch: cùng màu với bi đứng yên gần đó và khác màu bi mục tiêu
                if x[2] != obb[2] and any(st[2] == x[2] and _d(x, st) < 30 and not any(_d(y, st) < 1.5 for y in s['b'])
                                          for st in statics): continue
                v = (x[0]-obb[0], x[1]-obb[1])
                if math.hypot(*v) <= max(0.8, _d(last, obb)) or _d(x, last) > 60: continue
                if dir0 and _ang(v, dir0) > 10: continue
                # điểm đầu tiên: bi vào lỗ lăn gần như thẳng tới lỗ -> phải nằm đúng hướng một lỗ (loại bi cái bị nhận nhầm màu)
                if not dir0 and min(_ang(v, (P[0]-obb[0], P[1]-obb[1])) for P in POCKETS) > 6: continue
                cands.append(x)
            if cands and not occluded:
                x = min(cands, key=lambda x: _d(x, last)); last, tlast = x, s['t']; npts += 1
                if dir0 is None: dir0 = (x[0]-obb[0], x[1]-obb[1])
        pocket = None
        if tlast:
            dist = [_d(last, P) for P in POCKETS]; k = min(range(6), key=lambda k: dist[k])
            if dist[k] < 14: pocket = k
            else:   # bi chưa tới lỗ ở khung cuối thấy được: chọn lỗ nằm đúng hướng lăn
                mv = (last[0]-obb[0], last[1]-obb[1]); L = math.hypot(*mv)
                if L > 3 and (npts >= 2 or last[2] == obb[2]):   # một điểm duy nhất: chỉ tin khi đúng màu bi
                    best = min(range(6), key=lambda k: _ang(mv, (POCKETS[k][0]-obb[0], POCKETS[k][1]-obb[1])))
                    if _ang(mv, (POCKETS[best][0]-obb[0], POCKETS[best][1]-obb[1])) < 8: pocket = best
        ev.append({'A': A, 'B': B, 'cb': ca, 'ob': obb, 'stroke': stroke, 'ob_last': last[:2] if tlast else None,
                   't_vanish': tlast, 'pocket_tracked': pocket, 'note': note, 'cue_after': cb is not None})
    return ev

# ------------------------------------------------------------------ 4. đo chính xác
def valid_pockets(cb, ob):
    out = []
    for k in range(6):
        th, ov, slot, D, lp = geom_theta(cb, ob, k)
        A = aim_points()[k]; u = ((A[0]-ob[0])/lp, (A[1]-ob[1])/lp); gb = (ob[0]-u[0]*2*R, ob[1]-u[1]*2*R)
        if th < 85 and R-0.01 <= gb[0] <= 100-R+0.01 and R-0.01 <= gb[1] <= 50-R+0.01: out.append((k, th))
    return sorted(out, key=lambda x: x[1])

def measure(video, cal, e, want=4):
    """Đo thế bi trên vài khung full-res cuối cùng của thế đứng yên trước cú đánh; lấy trung vị."""
    A = e['A']; ts = sorted(A['ts'], reverse=True)
    tries = [t for t in ts if t >= A['t1']-8][:10]
    got = []
    for t in tries:
        im = grab(video, t)
        if not im: continue
        bs = detect_full_img(im, cal)
        cbs = [b for b in bs if plain_white(b) and _d(b['table'], e['cb']) < 5]
        obs = [b for b in bs if _d(b['table'], e['ob']) < 4 and b not in cbs]
        if obs and not cbs and len(e['cb']) > 3:          # bi cái dính đầu cơ / tay: khớp bán kính cố định từ vị trí thô
            cbs = [refine_at(im, cal, e['cb'][3])]
            cbs = [b for b in cbs if b and _d(b['table'], e['cb']) < 5]
        if cbs and obs:
            got.append((t, min(cbs, key=lambda b: _d(b['table'], e['cb'])), min(obs, key=lambda b: _d(b['table'], e['ob']))))
            if len(got) >= want: break
    if not got: return None
    med = lambda k: [statistics.median(g[k]['table'][i] for g in got) for i in range(2)]
    cb, ob = med(1), med(2)
    spread = max(max(_d(g[1]['table'], cb), _d(g[2]['table'], ob)) for g in got)
    return {'t_pre': got[0][0], 'cb': {'table': cb}, 'ob': {'table': ob, 'r_px': got[0][2]['r_px']},
            'still': len(got) >= 2 and spread < 0.3, 'spread': round(spread, 2), 'n_frames': len(got)}

def refine_at(im, cal, px):
    cam = cal['camera']; cx, cy = float(px[0]), float(px[1])
    bed = im.get(int(cx), int(min(1079, cy+40)))
    for _ in range(4):
        u, v = ray_plane(cam, (cx, cy), -R); _, zc = project(cam, (u, v, -R)); r = cam[6]*R/zc
        cx, cy = refine(im, cx, cy, r, bed, lambda x, y, m: True)
    u, v = ray_plane(cam, (cx, cy), -R)
    return {'table': [u, v], 'px': [cx, cy], 'r_px': r}

def detect_full_img(im, cal):
    import balls as B
    path = os.path.join(os.environ.get('TEMP', '.'), f'_shotscan_{os.getpid()}.ppm')
    with open(path, 'wb') as f: f.write(b'P6\n1920 1080\n255\n'+bytes(im.px))
    try: return B.detect(path, cal)
    finally: os.remove(path)

# ------------------------------------------------------------------ 5. báo cáo
def report(outdir, video, shots, cal):
    os.makedirs(os.path.join(outdir, 'thumbs'), exist_ok=True)
    rows = []
    for s in shots:
        for tag, t in (('pre', s['t_pre']), ('post', s['t_post'])):
            fn = os.path.join(outdir, 'thumbs', f"{s['id']}_{tag}.jpg")
            if not os.path.exists(fn):
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', video, '-frames:v', '1', '-vf', 'scale=960:-1', '-q:v', '4', fn])
        cam = cal['camera']; px = lambda P: project(cam, (P[0], P[1], -R))[0]
        r = s['r_px']; circ = ''.join(f'<circle cx="{px(b)[0]:.1f}" cy="{px(b)[1]:.1f}" r="{r*1.5:.1f}" class="{c}"/>' for b, c in ((s['cb'], 'cb'), (s['ob'], 'ob')))
        for k, th in s['pockets']:
            P = project(cam, (*POCKETS[k], 0))[0]
            circ += f'<circle cx="{P[0]:.1f}" cy="{P[1]:.1f}" r="22" class="pk{"" if k == s["pocket"] else " alt"}"/><text x="{P[0]+24:.0f}" y="{P[1]-8:.0f}">{k}: {th:.1f}°</text>'
        conf = {'high': 'Cao', 'medium': 'Vừa', 'low': 'Thấp'}[s['confidence']]
        rows.append(f'''<tr class="{s['confidence']}"><td><b>{s['id']}</b><br>{fmt(s['clip'][0])} – {fmt(s['clip'][1])}<br>bi {s['ob_color']}<br>
<b class="th">θ {s['angle']:.1f}°</b><br>lỗ {s['pocket']}{' (theo dõi được)' if s['pocket_tracked'] else ' (suy đoán)'}<br>tin cậy: <b>{conf}</b><br><small>{'; '.join(s['notes'])}</small></td>
<td><div class="im"><img src="thumbs/{s['id']}_pre.jpg"><svg viewBox="0 0 1920 1080">{circ}</svg></div>trước cú đánh · {fmt(s['t_pre'])}</td>
<td><div class="im"><img src="thumbs/{s['id']}_post.jpg"></div>sau · {fmt(s['t_post'])}</td></tr>''')
    html = f'''<!DOCTYPE html><html lang="vi"><meta charset="utf-8"><title>Shots – {os.path.basename(video)}</title>
<style>body{{font:14px system-ui;background:#111;color:#ddd;margin:20px}}table{{border-collapse:collapse}}td{{vertical-align:top;padding:8px;border-bottom:1px solid #333}}
.im{{position:relative;width:480px}}.im img{{width:100%;display:block}}.im svg{{position:absolute;inset:0;width:100%;height:100%}}
circle{{fill:none;stroke-width:4}}.cb{{stroke:#fff}}.ob{{stroke:#ffd43b}}.pk{{stroke:#3dd6c4;stroke-width:5}}.pk.alt{{stroke:#3dd6c4;stroke-dasharray:6 6;stroke-width:3}}
text{{fill:#3dd6c4;font-size:30px;font-weight:700}}.th{{color:#ffd43b;font-size:18px}}tr.low{{opacity:.6}}small{{color:#999}}</style>
<h2>{len(shots)} cú vào lỗ · {os.path.basename(video)}</h2>
<p>Duyệt rồi cắt: <code>python cut_shots.py "{os.path.join(outdir, 'shots.json')}" --ids ID1,ID2</code> hoặc <code>--min-conf high</code></p>
<table>{''.join(rows)}</table></html>'''
    open(os.path.join(outdir, 'report.html'), 'w', encoding='utf-8').write(html)

def fmt(t): return f'{int(t//3600)}:{int(t%3600//60):02d}:{t%60:04.1f}' if t >= 3600 else f'{int(t//60)}:{t%60:04.1f}'

def short_id(video):
    b = os.path.splitext(os.path.basename(video))[0]
    if 'Media_' in b: return b.split('Media_')[1][:11]
    # video đã có clip trong thư viện: giữ tiền tố cũ (không đổi id/tên file clip đã cắt)
    jf = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'clips', 'clips.json')
    if os.path.exists(jf):
        old = next((e['id'].rsplit('-', 1)[0] for e in json.load(open(jf, encoding='utf-8'))
                    if (e.get('src') or {}).get('video') == os.path.basename(video) and (e.get('src') or {}).get('auto')), None)
        if old: return old
    import unicodedata, hashlib                                         # tên file clip: chỉ ASCII (vd "Dương" -> "duong")
    h = hashlib.md5(os.path.basename(video).encode('utf-8')).hexdigest()[:4]   # nhiều trận cùng cơ thủ: 16 ký tự đầu trùng nhau
    b = unicodedata.normalize('NFKD', b.replace('đ', 'd').replace('Đ', 'D')).encode('ascii', 'ignore').decode()
    return ''.join(ch for ch in b if ch.isalnum())[:16].lower() + h

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('video'); ap.add_argument('--out', default=None)
    ap.add_argument('--fps', type=float, default=2.0); ap.add_argument('--stage', default='all')
    ap.add_argument('--calib', help='dùng file hiệu chỉnh có sẵn (vd. calib/usopen2023-final.json) thay vì tự hiệu chỉnh')
    a = ap.parse_args()
    video = os.path.abspath(a.video)
    root = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scan_out')
    outdir = os.path.join(root, os.path.splitext(os.path.basename(video))[0][:80]); os.makedirs(outdir, exist_ok=True)
    dur, vfps = probe(video); print(f'{os.path.basename(video)}: {dur/60:.1f} phút, {vfps:g} fps')
    cf = os.path.join(outdir, 'calib.json')
    if a.calib: cal = json.load(open(a.calib, encoding='utf-8')); json.dump(cal, open(cf, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    elif os.path.exists(cf): cal = json.load(open(cf, encoding='utf-8'))
    else:
        print('1) Hiệu chỉnh camera…'); cal = calibrate_video(video, dur); json.dump(cal, open(cf, 'w'), indent=1)
    set_view(cal)                                                    # nỉ màu (vd WPA 2025 xanh dương), camera trên xuống
    print(f'   camera: {[round(v, 2) for v in cal["camera"]]}  rms {cal["fit_rms_px"]:.2f}px  ({len(cal.get("frames_used", [])) or "file có sẵn"} khung)')
    if 'rail_ref' not in cal and cal.get('frames_used'):
        cal['rail_ref'] = learn_rail(video, cal); json.dump(cal, open(cf, 'w'), indent=1)
        if cal['rail_ref']: print('   bàn băng sáng: dùng màu băng học từ khung hiệu chỉnh để nhận camera đầu bàn')
    if a.stage == 'calib': return
    print('2) Quét nhanh…'); sig = scan(video, dur, cal['camera'], outdir, a.fps, rail_ref=cal.get('rail_ref'))
    print(f'   {sum(s["ov"] for s in sig)}/{len(sig)} mẫu là camera trên cao')
    if a.stage == 'scan': return
    print('3) Tìm sự kiện…'); lay = stable_layouts(sig); ev = find_events(sig, lay)
    print(f'   {len(lay)} thế bi đứng yên, {len(ev)} cú vào lỗ ứng viên')
    print('4) Đo chính xác…'); shots = []; sid = short_id(video)
    for e in ev:
        m = measure(video, cal, e)
        if not m: print(f'   bỏ {fmt(e["A"]["t1"])}: không đo được bi cái/bi mục tiêu'); continue
        cb, ob = m['cb']['table'], m['ob']['table']
        ob = [ob[0], min(max(ob[1], R), 50-R)]; ob[0] = min(max(ob[0], R), 100-R)
        vp = valid_pockets(cb, ob); notes = []
        if not vp: print(f'   bỏ {fmt(m["t_pre"])}: không có lỗ nào hợp lệ'); continue
        if e['pocket_tracked'] is not None and e['pocket_tracked'] in [k for k, _ in vp]: pocket = e['pocket_tracked']
        else:
            pocket = vp[0][0]
            notes.append('lỗ chưa theo dõi được – đang chọn lỗ có θ nhỏ nhất' if len(vp) > 1 else 'chỉ một lỗ hợp lệ')
        th = dict(vp)[pocket]
        tracked = e['pocket_tracked'] is not None and e['pocket_tracked'] in [k for k, _ in vp]
        clear = len(vp) == 1 or vp[1][1] > 70                      # lỗ khác đòi góc > 70°: gần như chắc chắn
        conf = 'high' if (tracked and m['still']) else ('medium' if (tracked or clear) else 'low')
        if m['spread'] > 0.5: conf = 'low'                           # các khung đo không khớp nhau
        if not m['still']: notes.append(f"chưa xác nhận bi đứng yên ({m['n_frames']} khung, lệch {m['spread']}\")")
        if e['note']: notes.append(e['note'])
        # khung cắt: biết lúc đánh -> quanh lúc đánh; không biết (đang chiếu cận cảnh) -> giữ tới khi bi rơi / thế mới hiện ra
        t_pre, t_post = m['t_pre'], e['B']['t0']
        end = (e['t_vanish']+2.5) if e['t_vanish'] else t_post+1
        if e['stroke'] is not None: start = max(0, e['stroke']-4); end = max(min(end, start+18), start+10)   # đủ thời gian thấy bi rơi
        else:
            start = max(0, t_pre-4); end = min(end, start+44)
            if e['t_vanish'] is None:
                notes.append('cú đánh diễn ra ngoài camera trên cao – kiểm tra khung cắt' + (' (khoảng trống dài, clip có thể thiếu cú đánh)' if t_post-t_pre > 40 else ''))
        shots.append({'id': f'{sid}-{int(t_pre*10):06d}', 'video': video, 'fps': vfps, 't_pre': round(t_pre, 2), 't_post': round(t_post, 2),
                      'stroke': e['stroke'], 't_vanish': e['t_vanish'], 'clip': [round(start, 2), round(end, 2)],
                      'cb': [round(v, 2) for v in cb], 'ob': [round(v, 2) for v in ob], 'ob_color': e['ob'][2], 'r_px': m['ob']['r_px'],
                      'pocket': pocket, 'pocket_tracked': e['pocket_tracked'] is not None, 'pockets': [[k, round(t, 1)] for k, t in vp],
                      'angle': round(th, 1), 'confidence': conf, 'notes': notes})
        print(f'   {shots[-1]["id"]}  {fmt(t_pre)}  bi {e["ob"][2]:7s} lỗ {pocket}  θ {th:5.1f}°  [{conf}]')
    json.dump(shots, open(os.path.join(outdir, 'shots.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    report(outdir, video, shots, cal)
    print(f'Xong: {len(shots)} cú → {os.path.join(outdir, "report.html")}')

if __name__ == '__main__':
    main()
