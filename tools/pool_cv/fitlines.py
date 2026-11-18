import sys,json
def robust(pts,vert):
    P=[(p[1],p[0]) if vert else (p[0],p[1]) for p in pts if p]
    sl=sorted((P[j][1]-P[i][1])/(P[j][0]-P[i][0]) for i in range(len(P)) for j in range(i+1,len(P)) if P[j][0]!=P[i][0])
    a=sl[len(sl)//2]; b=sorted(p[1]-a*p[0] for p in P)[len(P)//2]
    for _ in range(3):
        I=[p for p in P if abs(p[1]-(a*p[0]+b))<=2.0]
        n=len(I); sx=sum(p[0] for p in I); sy=sum(p[1] for p in I)
        sxx=sum(p[0]**2 for p in I); sxy=sum(p[0]*p[1] for p in I)
        a=(n*sxy-sx*sy)/(n*sxx-sx*sx); b=(sy-a*sx)/n
    return a,b,n
def inter(V,H):
    a,b,_=V;c,e,_=H
    y=(c*b+e)/(1-c*a); return (a*y+b,y)
def corners(d):
    L=robust(d['L'],1);R=robust(d['R'],1);T=robust(d['T'],0);B=robust(d['B'],0)
    return {'lines':{'L':L,'R':R,'T':T,'B':B},'TL':inter(L,T),'TR':inter(R,T),'BL':inter(L,B),'BR':inter(R,B)}
if __name__=='__main__':
    c=corners(json.load(open(sys.argv[1])))
    for k,v in c['lines'].items(): print(k,'%.4f %.2f n=%d'%v)
    print(json.dumps({k:[round(c[k][0],1),round(c[k][1],1)] for k in ('TL','TR','BL','BR')}))
