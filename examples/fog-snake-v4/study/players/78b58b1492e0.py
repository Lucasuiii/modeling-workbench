import sys,json,heapq

class Player:
    def __init__(self):
        self.seen=set(); self.rocks=set(); self.food=set(); self.last_steps=-1
    def choose(self,o):
        w,h=o['size']; head=tuple(o['body'][0]); level=o['level']; r=o['radius']
        visible={(x,y) for x in range(w) for y in range(h) if abs(x-head[0])+abs(y-head[1])<=r}
        self.seen |= visible
        self.rocks |= {tuple(p) for p in o['rocks']}
        if level=='marsh': self.food=set(map(tuple,o['food']))
        else:
            self.food-=visible
            self.food|=set(map(tuple,o['food']))
        if level=='garden' and o['eaten']==6: return 'STOP'
        last=o.get('last_scan')
        if level=='marsh' and last and last['axis']=='SNIFF' and last['dist'] is None: return 'STOP'
        unknown={(x,y) for x in range(w) for y in range(h)}-self.seen
        if not unknown and not self.food:
            if level!='marsh': return 'STOP'
            if o['large_wait']==0: return 'SNIFF'
            self.seen=visible.copy(); unknown={(x,y) for x in range(w) for y in range(h)}-self.seen
        # Dijkstra through publicly known terrain, treating body as temporarily blocked.
        body=set(map(tuple,o['body'][1:-1])); dist={head:0}; first={}; heap=[(0,head)]
        dirs=[(1,0,'R'),(0,1,'D'),(-1,0,'L'),(0,-1,'U')]
        while heap:
            d,p=heapq.heappop(heap)
            if d!=dist[p]: continue
            for dx,dy,a in dirs:
                q=(p[0]+dx,p[1]+dy)
                if not(0<=q[0]<w and 0<=q[1]<h) or q in body: continue
                nd=d+(o['rock_move_cost'] if q in self.rocks else 1)
                if nd<dist.get(q,1e9):
                    dist[q]=nd; first[q]=first.get(p,a); heapq.heappush(heap,(nd,q))
        targets=[p for p in self.food if p in dist and p!=head]
        if targets:
            target=min(targets,key=lambda p:dist[p]); return first[target]
        # A location's benefit is newly observed cells, discounted by travel distance.
        best=None
        for p,d in dist.items():
            if p==head: continue
            gain=sum((p[0]+dx,p[1]+dy) in unknown for dx in range(-r,r+1) for dy in range(-r,r+1) if abs(dx)+abs(dy)<=r)
            if gain:
                score=(d+1)/gain
                item=(score,d,p)
                if best is None or item<best: best=item
        if best: return first[best[2]]
        # Keep moving to release the tail or await a sniff.
        for dx,dy,a in dirs:
            q=(head[0]+dx,head[1]+dy)
            if 0<=q[0]<w and 0<=q[1]<h and q not in body and q not in self.food: return a
        return 'STOP'

p=Player()
for line in sys.stdin:
    print(p.choose(json.loads(line)),flush=True)
