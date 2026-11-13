"""Calibrate the overhead broadcast camera from one clean overhead frame (no player over the rails).
usage: python calibrate.py frame.ppm out.json [--ref calib/old.json]

Detects 5 image lines and fits a pinhole camera (see camera.py) by point-to-line distance:
  L, R : side cushion noses     world y=0 / y=50,  z=-1.43
  T    : far cushion base       world x=100,       z=0
  FS   : foot string chalk line world x=75,        z=0
  N    : near cushion nose silhouette (subtle brightness step just above the bright near-cushion top)
         world x=0, z=-1.43
These assignments gave RMS 0.74px on the US Open 2023 final (alternatives 3-6px).
Scan windows are tuned for that framing (table ~ x 490..1430, y 375..880 at 1920x1080);
for another framing adjust ROWS/XL/XR/FS_WIN/N_WIN below.
The solver can fall into a mirror solution (camera below the bed, Z>0): we start above the
table and reject Z>0."""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppm import Img
from fitlines import robust
from linefit import fit_lines

ROWS = (380, 870)          # rows scanned for L/R
XL, XR = 720, 1200          # start columns for L/R scans (outside the cloth marks at x~845/1083)
T_COLS = (620, 1330)        # columns scanned for T (upwards from FS_START)
T_START = 640
FS_WIN = (462, 500)         # rows where the foot string is searched
FS_SKIP = [(830, 860), (1070, 1100)]  # columns of vertical cloth marks
N_WIN = (862, 880)          # rows where the near nose step is searched
P0 = [-309, 25.7, -115, 0.0, 0.3, 0.0, 6128]

def scan(im, x, y, dx, dy, TH=20, n=3):
    hist = []; miss = 0; last = (x, y)
    while 2 < x < im.w-2 and 2 < y < im.h-2:
        c = im.get(x, y)
        dif = sum(abs(c[i]-sum(h[i] for h in hist)/len(hist)) for i in range(3)) if len(hist) >= 8 else 0
        if dif < TH: miss = 0; last = (x, y); hist.append(c); hist = hist[-15:]
        else:
            miss += 1
            if miss >= n: return last
        x += dx; y += dy
    return None

def detect_lines(im):
    L = [scan(im, XL, y, -1, 0) for y in range(ROWS[0], ROWS[1], 6)]
    R = [scan(im, XR, y, 1, 0) for y in range(ROWS[0], ROWS[1], 6)]
    T = [scan(im, x, T_START, 0, -1) for x in range(T_COLS[0], T_COLS[1], 8)]
    fs = []
    for x in range(T_COLS[0]+10, T_COLS[1]-30, 6):
        if any(a <= x <= b for a, b in FS_SKIP): continue
        f = lambda yy: sum(im.get(x, yy)) - (sum(im.get(x, yy-3)) + sum(im.get(x, yy+3)))/2
        d0, y = max((f(yy), yy) for yy in range(*FS_WIN))
        if d0 <= 4: continue
        a, b, c = f(y-1), f(y), f(y+1); den = a-2*b+c
        fs.append([x, y + (0.5*(a-c)/den if den else 0)])
    N = []
    for x in range(560, 1380, 8):
        base = sum(im.get(x, N_WIN[0]))
        for y in range(N_WIN[0]+1, N_WIN[1]):
            if sum(im.get(x, y)) - base >= 7: N.append([x, y-0.5]); break
    out = {}
    for k, pts, vert in (('L', L, 1), ('R', R, 1), ('T', T, 0), ('FS', fs, 0), ('N', N, 0)):
        a, b, n = robust(pts, vert); out[k] = {'form': 'x=a*y+b' if vert else 'y=a*x+b', 'a': a, 'b': b, 'n': n}
    return out

def calibrate(path, hs=1.43, hf=0.0, hn=1.43):
    im = Img(path); lines = detect_lines(im)
    ln = lambda k: ('v' if lines[k]['form'].startswith('x') else 'h', lines[k]['a'], lines[k]['b'])
    cons = [(ln('L'), [(x, 0, -hs) for x in range(8, 96, 8) if not 44 < x < 56]),
            (ln('R'), [(x, 50, -hs) for x in range(8, 96, 8) if not 44 < x < 56]),
            (ln('T'), [(100, y, -hf) for y in range(4, 48, 4)]),
            (ln('FS'), [(75, y, 0) for y in range(4, 48, 4)]),
            (ln('N'), [(0, y, -hn) for y in range(4, 48, 4)])]
    p, cost, r = fit_lines(cons, P0)
    if p[2] > 0: raise SystemExit('mirror solution (camera below bed) - change P0')
    return p, math.sqrt(cost/len(r)), lines

if __name__ == '__main__':
    p, rms, lines = calibrate(sys.argv[1])
    print('camera', [round(v, 4) for v in p], 'rms_px', round(rms, 2))
    for k, v in lines.items(): print(k, v)
    if '--ref' in sys.argv:
        ref = json.load(open(sys.argv[sys.argv.index('--ref')+1]))
        for k, v in ref.get('image_lines', {}).items():
            if k in lines:
                L = lines[k]; x = 960 if L['form'].startswith('y') else None
                if x is not None: print(f'{k}: y@960 new {L["a"]*960+L["b"]:.1f} ref {v["a"]*960+v["b"]:.1f}')
                else: print(f'{k}: x@600 new {L["a"]*600+L["b"]:.1f} ref {v["a"]*600+v["b"]:.1f}')
    if len(sys.argv) > 2 and not sys.argv[2].startswith('--'):
        json.dump({'camera': p, 'camera_param_names': ['X', 'Y', 'Z', 'yaw', 'pitch', 'roll', 'f_px'], 'fit_rms_px': rms,
                   'image_lines': lines, 'image_size': [1920, 1080]}, open(sys.argv[2], 'w'), indent=1)
