import sys,json,heapq

class Player:
 def __init__(self):
  self.seen=set(); self.food=set(); self.rocks=set(); self.free=set(); self.last_steps=-1; self.cycle=0; self.scan_pending=False; self.scent=None; self.prev_eaten=0
 def choose(self,o):
  w,h=o['size']; head=tuple(o['body'][0]); body=[tuple(p) for p in o['body']]; r=o['radius']; marsh=o['level']=='marsh'
  if o['eaten']>self.prev_eaten: self.scent=None
  self.prev_eaten=o['eaten']
  if marsh and o['steps']!=self.last_steps and o['rustle']:
   self.scent=None
   x,y=head
   self.seen.difference_update((xx,yy) for xx in range(max(0,x-4),min(w,x+5)) for yy in range(max(0,y-4),min(h,y+5)))
   self.food.clear()
  visible={(x,y) for x in range(max(0,head[0]-r),min(w,head[0]+r+1)) for y in range(max(0,head[1]-r),min(h,head[1]+r+1)) if abs(x-head[0])+abs(y-head[1])<=r}
  rocks={tuple(p) for p in o['rocks']}; foods={tuple(p) for p in o['food']}
  self.seen.update(visible); self.rocks.update(rocks); self.free.update(visible-rocks)
  self.food.difference_update(visible); self.food.update(foods); self.food.discard(head)
  self.last_steps=o['steps']
  last=o['last_scan']
  if marsh and last and last['axis']=='SNIFF' and self.scan_pending:
   self.scan_pending=False
   if last['dist'] is None:return 'STOP'
   d=last['dist']; hx,hy=head
   # The nearest target is somewhere on this ring; all closer squares were empty.
   self.scent={(x,y) for x in range(w) for y in range(h) if abs(x-hx)+abs(y-hy)==d and (x,y) not in self.rocks}
   self.seen.update((x,y) for x in range(w) for y in range(h) if abs(x-hx)+abs(y-hy)<d)
  if self.scent is not None:
   self.scent.difference_update(visible-self.food)
   if not self.scent:self.scent=None
  if marsh and self.scent is None and not self.food and o['large_wait']==0:
   self.scan_pending=True; return 'SNIFF'
  if o['level']=='garden' and o['eaten']==6:return 'STOP'
  unseen={(x,y) for x in range(w) for y in range(h)}-self.seen-self.rocks
  if not unseen and not self.food:
   if not marsh:return 'STOP'
   if o['large_wait']==0:
    self.scan_pending=True; return 'SNIFF'
   self.seen.clear(); self.seen.update(visible); unseen={(x,y) for x in range(w) for y in range(h)}-self.seen-self.rocks
  if marsh and self.scent:
   unseen=self.scent-self.seen-self.rocks
   if not unseen:unseen=self.scent-self.rocks
  # Dijkstra with conservative body avoidance, accounting for tail movement.
  blocked=set(body[:-1]); blocked.discard(head)
  dist={head:0}; first={}; heap=[(0,head)]; best=None
  while heap:
   d,p=heapq.heappop(heap)
   if d!=dist[p]:continue
   if p!=head:
    # Prefer revealed food; exploring cells with the most unseen neighbors is efficient.
    if p in self.food:
     score=d-1000
    else:
     gain=sum((p[0]+dx,p[1]+dy) in unseen for dx,dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)))
     score=d+8/(gain or .01) if gain else 1e9
    if best is None or score<best[0]:best=(score,p)
   for act,dx,dy in [('R',1,0),('D',0,1),('L',-1,0),('U',0,-1)]:
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
