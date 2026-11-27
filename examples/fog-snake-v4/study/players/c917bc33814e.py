import sys,json,heapq

class Player:
    def __init__(self):
        self.seen=set(); self.rocks=set(); self.food=set(); self.constraints={}; self.pending=None; self.eaten=0
    def choose(self,o):
        w,h=o['size']; head=tuple(o['body'][0]); level=o['level']; r=o['radius']
        allcells={(x,y) for x in range(w) for y in range(h)}
        visible={(x,y) for x in range(max(0,head[0]-r),min(w,head[0]+r+1)) for y in range(max(0,head[1]-r),min(h,head[1]+r+1)) if abs(x-head[0])+abs(y-head[1])<=r}
        self.seen |= visible
        self.rocks |= {tuple(p) for p in o['rocks']}
        self.food-=visible; self.food|=set(map(tuple,o['food']))
        if o['eaten']>self.eaten:
            for k,(cells,n) in self.constraints.items():
                if head in cells: self.constraints[k]=(cells,n-1)
            self.eaten=o['eaten']
        if self.pending is not None:
            key,cells=self.pending; last=o['last_scan']
            if last and last.get('count') is not None: self.constraints[key]=(cells,last['count'])
            self.pending=None
        if level=='garden' and o['eaten']==6: return 'STOP'
        # Exact counts allow us to discard all remaining unknown cells when every
        # remaining food in that region has already been seen.
        for cells,n in self.constraints.values():
            if n==len(cells & self.food): self.seen |= cells-self.food
        unknown=allcells-self.seen-self.rocks
        if not unknown and not self.food: return 'STOP'
        snake=list(map(tuple,o['body'])); body=set(snake[1:-1]); dirs=[(1,0,'R'),(0,1,'D'),(-1,0,'L'),(0,-1,'U')]
        def safe(q):
            grow=q in self.food
            if q in (snake if grow else snake[:-1]): return False
            newbody=[q]+(snake if grow else snake[:-1])
            if len(newbody)<=2: return True
            blocked=set(newbody[1:-1]); tail=newbody[-1]; stack=[q]; visited={q}
            while stack:
                p=stack.pop()
                if p==tail: return True
                for dx,dy,_ in dirs:
                    z=(p[0]+dx,p[1]+dy)
                    if 0<=z[0]<w and 0<=z[1]<h and z not in blocked and z not in visited:
                        visited.add(z); stack.append(z)
            return False
        legal=[(head[0]+dx,head[1]+dy,a) for dx,dy,a in dirs if 0<=head[0]+dx<w and 0<=head[1]+dy<h]
        legal=[(x,y,a) for x,y,a in legal if (x,y) not in snake[:-1] and ((x,y) not in self.food or (x,y) not in snake)]
        safe_moves=[(x,y,a) for x,y,a in legal if safe((x,y))] or legal
        dist={head:0}; first={}; heap=[]
        for x,y,a in safe_moves:
            q=(x,y); d=o['rock_move_cost'] if q in self.rocks else 1
            dist[q]=d; first[q]=a; heapq.heappush(heap,(d,q))
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
        if targets: return first[min(targets,key=lambda p:dist[p])]
        # Probe windows in proximity, so rich areas are identified while traversing.
        windows=[]
        for box in o['windows']:
            cells={(x,y) for x in range(box['x'],box['x']+box['side']) for y in range(box['y'],box['y']+box['side'])}
            windows.append(cells)
        if level in ('orchard','cellar') and o['large_wait']==0:
            choices=[]
            for i,cells in enumerate(windows):
                if ('B',i) in self.constraints or len(cells&unknown)<4: continue
                near=min((dist[p] for p in cells if p in dist),default=999)
                choices.append((near,i,cells))
            if choices:
                _,i,cells=min(choices); self.pending=(('B',i),cells); return 'BOX '+str(i)
        # Once grove probes are established, line scans cover the orchard corridor.
        if level=='orchard' and all(('B',i) in self.constraints or not (cells&unknown) for i,cells in enumerate(windows)):
            lines=[('COL',x,{(x,y) for y in range(h)}) for x in range(7,13)]+[('ROW',y,{(x,y) for x in range(w)}) for y in (7,8)]
            options=[]
            for axis,i,cells in lines:
                if (axis,i) not in self.constraints and len(cells&unknown)>=3:
                    options.append((-len(cells&unknown),axis,i,cells))
            if options:
                _,axis,i,cells=min(options); self.pending=((axis,i),cells); return f'{axis} {i}'
        # Estimated density from current exact counts; unexplored corridors get low prior.
        weights={p:(0.035 if level in ('orchard','cellar') else 1.0) for p in unknown}
        for i,cells in enumerate(windows):
            inside=cells&unknown
            if not inside: continue
            c=self.constraints.get(('B',i))
            density=max(0,(c[1]-len(cells&self.food))/len(inside)) if c else (0.12 if level=='orchard' else 0.08)
            for p in inside: weights[p]=density
        for key,(cells,n) in self.constraints.items():
            if key[0]=='B': continue
            inside=cells&unknown
            if inside:
                density=max(0,(n-len(cells&self.food))/len(inside))
                for p in inside: weights[p]=min(weights[p],density) if any(p in a for a in windows) else density
        best=None
        for p,d in dist.items():
            if p==head: continue
            gain=sum(weights.get((p[0]+dx,p[1]+dy),0) for dx in range(-r,r+1) for dy in range(-r,r+1) if abs(dx)+abs(dy)<=r)
            if gain>0:
                item=((d+1)/gain,d,p)
                if best is None or item<best: best=item
        if best: return first[best[2]]
        for dx,dy,a in dirs:
            q=(head[0]+dx,head[1]+dy)
            if 0<=q[0]<w and 0<=q[1]<h and q not in body and q not in self.food: return a
        return 'STOP'

p=Player()
for line in sys.stdin: print(p.choose(json.loads(line)),flush=True)
