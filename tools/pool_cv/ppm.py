def load(path):
    d=open(path,'rb').read()
    # parse header P6 w h max
    parts=[];i=0
    while len(parts)<4:
        while d[i:i+1].isspace(): i+=1
        if d[i:i+1]==b'#':
            while d[i:i+1]!=b'\n': i+=1
            continue
        j=i
        while not d[j:j+1].isspace(): j+=1
        parts.append(d[i:j]); i=j
    i+=1
    w,h=int(parts[1]),int(parts[2])
    return w,h,d[i:]
class Img:
    def __init__(s,path):
        s.w,s.h,s.px=load(path)
    def get(s,x,y):
        o=(y*s.w+x)*3; p=s.px; return p[o],p[o+1],p[o+2]
    @classmethod
    def from_raw(cls, w, h, data):
        o = cls.__new__(cls); o.w, o.h, o.px = w, h, data; return o
