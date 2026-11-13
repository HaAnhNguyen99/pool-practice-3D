import sys,os; sys.path.insert(0,os.path.dirname(__file__))
from ppm import Img
im=Img(sys.argv[1])
TH=int(sys.argv[2]) if len(sys.argv)>2 else 30
def scan(x,y,dx,dy,n=3):
    hist=[];miss=0;last=(x,y)
    while 2<x<im.w-2 and 2<y<im.h-2:
        c=im.get(x,y)
        if len(hist)>=8:
            m=[sum(h[i] for h in hist)/len(hist) for i in range(3)]
            dif=sum(abs(c[i]-m[i]) for i in range(3))
        else: dif=0
        if dif<TH:
            miss=0;last=(x,y);hist.append(c);hist=hist[-15:]
        else:
            miss+=1
            if miss>=n: return last
        x+=dx;y+=dy
    return None
def fit(pts):  # fit x = a*y+b or y=a*x+b with iterative outlier rejection
    pass
import json
XL=int(sys.argv[3]) if len(sys.argv)>3 else 720
XR=int(sys.argv[4]) if len(sys.argv)>4 else 1200
out={'L':[],'R':[],'T':[],'B':[]}
for y in range(380,870,6):
    out['L'].append(scan(XL,y,-1,0)); out['R'].append(scan(XR,y,1,0))
for x in range(620,1330,8):
    out['T'].append(scan(x,640,0,-1)); out['B'].append(scan(x,640,0,1))
print(json.dumps(out))
