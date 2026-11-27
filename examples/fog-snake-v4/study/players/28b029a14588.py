import json,sys,heapq

class Player:
 def __init__(self):
  self.seen=set(); self.rocks=set(); self.food=set(); self.counts={}; self.scanned=set(); self.prev_eaten=0; self.last_step=-1; self.pending=None
 def choose(self,o):
  w,h=o['size']; head=tuple(o['body'][0]); body=[tuple(p) for p in o['body']]; level=o['level']; r=o['radius']; vis=set()
  for dy in range(-r,r+1):
   for dx in range(-r,r+1):
    p=(head[0]+dx,head[1]+dy)
    if abs(dx)+abs(dy)<=r and 0<=p[0]<w and 0<=p[1]<h: vis.add(p)
  if level=='marsh' and o['steps']!=self.last_step and o['rustle']:
   self.seen.difference_update((x,y) for x in range(w) for y in range(h) if abs(x-head[0])+abs(y-head[1])<=3)
   self.food.difference_update((x,y) for x,y in list(self.food) if abs(x-head[0])+abs(y-head[1])<=3)
  self.seen.update(vis); self.rocks.difference_update(vis); self.rocks.update(map(tuple,o['rocks']))
  self.food.difference_update(vis); self.food.update(map(tuple,o['food']))
  if o['eaten']>self.prev_eaten:
   for i,(cells,count) in list(self.counts.items()):
    if head in cells: self.counts[i]=(cells,count-1)
  self.prev_eaten=o['eaten']; self.last_step=o['steps']
  scan=o['last_scan']
  if self.pending and scan:
   kind,i,cells=self.pending
   if scan['axis']==kind:
    if kind=='SNIFF':
     if scan['dist'] is None: return 'STOP'
     # The nearest target is at least dist away.
     d=scan['dist']; self.seen.update((x,y) for x in range(w) for y in range(h) if abs(x-head[0])+abs(y-head[1])<d)
    else:
     self.scanned.add((kind,i)); self.counts[(kind,i)]=(cells,scan['count'])
   self.pending=None
  for cells,count in self.counts.values():
   if count<=len(self.food & cells): self.seen.update(cells - self.food)
  if level=='garden' and o['eaten']==6: return 'STOP'
  # A scan identifies whole empty/fully-known orchard windows, even from afar.
  if level in ('orchard','cellar') and o['large_wait']==0:
   choices=[]
   for win in o['windows']:
    i=win['id']; cells={(x,y) for x in range(win['x'],win['x']+win['side']) for y in range(win['y'],win['y']+win['side'])}
    unknown=len(cells-self.seen-self.food)
    if ('BOX',i) not in self.scanned and unknown>=12:
     choices.append((unknown,i,cells))
   if choices:
    _,i,cells=max(choices); self.pending=('BOX',i,cells); return 'BOX '+str(i)
  unknown={(x,y) for x in range(w) for y in range(h)}-self.seen-self.food
  if not unknown and not self.food:
   if level!='marsh': return 'STOP'
   if o['large_wait']==0: self.pending=('SNIFF',0,set()); return 'SNIFF'
   # keep moving until sniff is ready
  # Dijkstra through known obstacles; permanent body blocking is conservative.
  blocked=set(body[1:-1]); dist={head:0}; first={}; heap=[(0,head)]
  moves=[(1,0,'R'),(0,1,'D'),(-1,0,'L'),(0,-1,'U')]
  safe=set()
  for dx,dy,a in moves:
   q=(head[0]+dx,head[1]+dy)
   if not(0<=q[0]<w and 0<=q[1]<h) or q in body[:-1] or (q==body[-1] and q in self.food): continue
   wall=set(body[:-1] if q not in self.food else body); wall.discard(q)
   reached={q}; queue=[q]
   for v in queue:
    for ex,ey,_ in moves:
     z=(v[0]+ex,v[1]+ey)
     if 0<=z[0]<w and 0<=z[1]<h and z not in wall and z not in reached: reached.add(z); queue.append(z)
   if len(reached)>=len(body)+2: safe.add(a)
  while heap:
   d,p=heapq.heappop(heap)
   if d!=dist[p]: continue
   for dx,dy,a in moves:
    q=(p[0]+dx,p[1]+dy)
    if not(0<=q[0]<w and 0<=q[1]<h) or q in blocked or (q==body[-1] and q in self.food) or (p==head and safe and a not in safe): continue
    nd=d+(o['rock_move_cost'] if q in self.rocks else 1)
    if nd<dist.get(q,1e9): dist[q]=nd; first[q]=a if p==head else first[p]; heapq.heappush(heap,(nd,q))
  # Prefer food over unexplored territory, and exploration positions exposing many cells.
  best=None
  for p,d in dist.items():
   if p==head: continue
   gain=sum((p[0]+dx,p[1]+dy) in unknown for dx in range(-r,r+1) for dy in range(-r,r+1) if abs(dx)+abs(dy)<=r)
   if p in self.food: score=d-8
   elif gain: score=d/(gain**0.7)+3
   else: continue
   item=(score,d,p)
   if best is None or item<best: best=item
  if best: return first[best[2]]
  if level=='marsh' and o['large_wait']==0: self.pending=('SNIFF',0,set()); return 'SNIFF'
  if len(dist)>1: return first[min((p for p in dist if p!=head),key=lambda p:dist[p])]
  for dx,dy,a in moves:
   p=(head[0]+dx,head[1]+dy)
   if 0<=p[0]<w and 0<=p[1]<h and p not in body[:-1]: return a
  return 'STOP'

p=Player()
for line in sys.stdin:
 try: print(p.choose(json.loads(line)),flush=True)
 except Exception as e: print(repr(e),file=sys.stderr); raise
