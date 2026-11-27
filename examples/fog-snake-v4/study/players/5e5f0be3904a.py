import sys,json,heapq

class Player:
 def __init__(self):
  self.seen=set(); self.food=set(); self.rocks=set(); self.free=set(); self.last_steps=-1; self.cycle=0; self.scan_pending=False; self.boxes={}; self.rows={}; self.pending=None; self.prev_eaten=0; self.rays={}; self.corridor_eaten=0
 def choose(self,o):
  w,h=o['size']; head=tuple(o['body'][0]); body=[tuple(p) for p in o['body']]; r=o['radius']; marsh=o['level']=='marsh'
  if marsh and o['steps']!=self.last_steps and o['rustle']:
   x,y=head
   self.seen.difference_update((xx,yy) for xx in range(max(0,x-4),min(w,x+5)) for yy in range(max(0,y-4),min(h,y+5)))
   self.food.clear()
  if o['eaten']>self.prev_eaten:
   if o['level']=='orchard' and not any(a['x']<=head[0]<a['x']+a['side'] and a['y']<=head[1]<a['y']+a['side'] for a in o['windows']):self.corridor_eaten+=1
   for win in o['windows']:
    if win['id'] in self.boxes and win['x']<=head[0]<win['x']+win['side'] and win['y']<=head[1]<win['y']+win['side']:
     self.boxes[win['id']]-=1
   if head[1] in self.rows:self.rows[head[1]]-=1
   for key,(cells,count) in list(self.rays.items()):
    if head in cells:self.rays[key]=(cells,count-1)
  self.prev_eaten=o['eaten']
  if self.pending is not None and o['last_scan']:
   typ,idx=self.pending
   if typ=='BOX':self.boxes[idx]=o['last_scan']['count']
   elif typ=='ROW':self.rows[idx]=o['last_scan']['count']
   else:
    y,direction=idx; hit=o['last_scan']['hit']; stop=hit[0] if hit else (-1 if direction=='R' else w)
    xs=range(w-1,stop,-1) if direction=='R' else range(stop)
    cells={(x,y) for x in xs}; self.rays[idx]=(cells,o['last_scan']['count'])
    self.free.update(cells)
    if hit:self.rocks.add(tuple(hit))
   self.pending=None
  visible={(x,y) for x in range(max(0,head[0]-r),min(w,head[0]+r+1)) for y in range(max(0,head[1]-r),min(h,head[1]+r+1)) if abs(x-head[0])+abs(y-head[1])<=r}
  rocks={tuple(p) for p in o['rocks']}; foods={tuple(p) for p in o['food']}
  self.seen.update(visible); self.rocks.update(rocks); self.free.update(visible-rocks)
  self.food.difference_update(visible); self.food.update(foods); self.food.discard(head)
  self.last_steps=o['steps']
  last=o['last_scan']
  if marsh and last and last['axis']=='SNIFF':
   if last['dist'] is None:return 'STOP'
   if self.scan_pending:
    self.seen.clear(); self.seen.update(visible); self.scan_pending=False
  if o['level']=='garden' and o['eaten']==6:return 'STOP'
  unseen={(x,y) for x in range(w) for y in range(h)}-self.seen-self.rocks
  if o['level'] in ('orchard','cellar'):
   if o['large_wait']==0 and len(self.boxes)<len(o['windows']):
    remaining=[win for win in o['windows'] if win['id'] not in self.boxes]
    # Nearby windows first, to start harvesting sooner.
    win=min(remaining,key=lambda a:abs(head[0]-(a['x']+a['side']//2))+abs(head[1]-(a['y']+a['side']//2)))
    self.pending=('BOX',win['id']); return 'BOX '+str(win['id'])
   for win in o['windows']:
    if self.boxes.get(win['id'], -1)==sum(win['x']<=p[0]<win['x']+win['side'] and win['y']<=p[1]<win['y']+win['side'] for p in self.food):
     unseen.difference_update((x,y) for x in range(win['x'],win['x']+win['side']) for y in range(win['y'],win['y']+win['side']))
   for y,c in self.rows.items():
    if c==sum(p[1]==y for p in self.food):unseen.difference_update((x,y) for x in range(w))
   for cells,count in self.rays.values():
    if count==len(cells & self.food):unseen.difference_update(cells)
   if o['level']=='orchard' and self.corridor_eaten==3:
    unseen={p for p in unseen if any(a['x']<=p[0]<a['x']+a['side'] and a['y']<=p[1]<a['y']+a['side'] for a in o['windows'])}
   if o['level']=='cellar' and len(self.boxes)==len(o['windows']) and sum(self.boxes.values())==0:
    candidates=[]
    for y in range(h):
     for direction in ('L','R'):
      if (y,direction) in self.rays:continue
      xs=range(w) if direction=='L' else range(w-1,-1,-1)
      segment=[]
      for x in xs:
       if (x,y) in self.rocks:break
       segment.append((x,y))
      n=sum(p in unseen for p in segment)
      if n>=4:candidates.append((n,y,direction))
    if candidates:
     _,y,direction=max(candidates); self.pending=('RAY',(y,direction)); return 'ROW %d %s'%(y,direction)
   # Scan rows when most large windows have been cleared.
   if o['level']=='orchard' and len(self.boxes)==len(o['windows']) and sum(self.boxes.values())==0:
    candidates=[(sum((x,y) in unseen for x in range(w)),y) for y in range(h) if y not in self.rows]
    if candidates and max(candidates)[0]>=4:
     y=max(candidates)[1]; self.pending=('ROW',y); return 'ROW '+str(y)
  if not unseen and not self.food:
   if not marsh:return 'STOP'
   if o['large_wait']==0:
    self.scan_pending=True; return 'SNIFF'
   self.seen.clear(); self.seen.update(visible); unseen={(x,y) for x in range(w) for y in range(h)}-self.seen-self.rocks
  # Dijkstra with conservative body avoidance, accounting for tail movement.
  blocked=set(body[:-1]); blocked.discard(head)
  actions=[('R',1,0),('D',0,1),('L',-1,0),('U',0,-1)]
  safe=set()
  for act,dx,dy in actions:
   q=(head[0]+dx,head[1]+dy)
   if not(0<=q[0]<w and 0<=q[1]<h) or q in blocked or (q==body[-1] and q in self.food):continue
   newbody=[q]+body if q in self.food else [q]+body[:-1]
   occupied=set(newbody[1:-1]); goal=newbody[-1]; queue=[q]; visited={q}
   for p in queue:
    for _,ax,ay in actions:
     z=(p[0]+ax,p[1]+ay)
     if 0<=z[0]<w and 0<=z[1]<h and z not in occupied and z not in visited:
      visited.add(z); queue.append(z)
   if goal in visited:safe.add(act)
  dist={head:0}; first={}; heap=[(0,head)]; best=None
  while heap:
   d,p=heapq.heappop(heap)
   if d!=dist[p]:continue
   if p!=head:
    # Prefer revealed food; exploring cells with the most unseen neighbors is efficient.
    if p in self.food:
     score=d-1000
    else:
     gain=0
     for dx,dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
      q=(p[0]+dx,p[1]+dy)
      if q not in unseen:continue
      weight=1.0
      if o['level'] in ('orchard','cellar'):
       wins=[a for a in o['windows'] if a['x']<=q[0]<a['x']+a['side'] and a['y']<=q[1]<a['y']+a['side']]
       weights=[]
       for a in wins:
        count=self.boxes.get(a['id'])
        if count is not None:
         size=sum((xx,yy) in unseen or (xx,yy) in self.food for xx in range(a['x'],a['x']+a['side']) for yy in range(a['y'],a['y']+a['side']))
         weights.append(max(0,count)/max(1,size))
       if weights:weight=0.05+min(weights)*15
       elif wins:weight=1.0
       else:weight=0.3
       if q[1] in self.rows:
        n=sum((x,q[1]) in unseen or (x,q[1]) in self.food for x in range(w))
        weight=min(weight,0.05+15*self.rows[q[1]]/max(1,n))
      gain+=weight
     score=d+8/(gain or .01) if gain else 1e9
    if best is None or score<best[0]:best=(score,p)
   for act,dx,dy in actions:
    if p==head and safe and act not in safe:continue
    q=(p[0]+dx,p[1]+dy)
    if not (0<=q[0]<w and 0<=q[1]<h) or q in blocked:continue
    nd=d+(o['rock_move_cost'] if q in self.rocks else 1)
    if nd<dist.get(q,1e9):dist[q]=nd; first[q]=act if p==head else first[p]; heapq.heappush(heap,(nd,q))
  if best:return first[best[1]]
  return 'STOP'

p=Player()
for line in sys.stdin:
 try: print(p.choose(json.loads(line)),flush=True)
 except Exception: print('STOP',flush=True)
