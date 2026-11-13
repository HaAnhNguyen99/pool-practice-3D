"""Port of index.html geom() theta: cut angle with ghost ball, pocket aim points as in the app."""
import math
R=1.125
def pockets(L=100,W=50):
    s=math.sqrt(0.5)
    P=[((0,0),(-s,-s),False),((L/2,0),(0,-1),True),((L,0),(s,-s),False),((0,W),(-s,s),False),((L/2,W),(0,1),True),((L,W),(s,s),False)]
    out=[]
    for (p,into,side) in P:
        aim=(p[0]+into[0]*0.3,p[1]+into[1]*0.3) if side else (p[0]-into[0]*1.0,p[1]-into[1]*1.0)
        out.append(aim)
    return out
def theta(cb,ob,pocket,L=100,W=50):
    A=pockets(L,W)[pocket]
    tp=(A[0]-ob[0],A[1]-ob[1]); lp=math.hypot(*tp); u=(tp[0]/lp,tp[1]/lp)
    gb=(ob[0]-u[0]*2*R,ob[1]-u[1]*2*R)
    v=(gb[0]-cb[0],gb[1]-cb[1]); D=math.hypot(*v); vn=(v[0]/D,v[1]/D)
    c=max(-1,min(1,vn[0]*u[0]+vn[1]*u[1])); th=math.degrees(math.acos(c))
    ov=max(0,1-math.sin(math.radians(th))); slot=round((1-math.sin(math.radians(min(th,89.9))))*8)
    return th,ov,slot,D,lp
