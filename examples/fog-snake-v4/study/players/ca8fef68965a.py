import json,sys,heapq

class Player:
 def __init__(self):
  self.seen=set(); self.rocks=set(); self.food=set(); self.rows={}; self.box={}; self.eaten=0; self.prev=None; self.pending=None; self.sniff=None
 def choose(self,o):
  w,h=o['size']; p=tuple(o['body'][0]); body=[tuple(q) for q in o['body']]; level=o['level']; radius=o['radius']
  if o['eaten']>self.eaten:
   if level!='marsh':
    for y in list(self.rows):
     if p[1]==y:self.rows[y]-=1
    for i in list(self.box):
     x,y,s=self.windows[i]
     if x<=p[0]<x+s and y<=p[1]<y+s:self.box[i]-=1
   self.eaten=o['eaten']
  self.windows=[(a['x'],a['y'],a['side']) for a in o['windows']] if o['windows'] and isinstance(o['windows'][0],dict) else o['windows']
  vis={(x,y) for x in range(max(0,p[0]-radius),min(w,p[0]+radius+1)) for y in range(max(0,p[1]-radius),min(h,p[1]+radius+1)) if abs(x-p[0])+abs(y-p[1])<=radius}
  self.seen|=vis; self.food-=vis; self.food|={tuple(q) for q in o['food']}; self.rocks|={tuple(q) for q in o['rocks']}
  scan=o.get('last_scan')
  if scan:
   if scan['axis']=='ROW':self.rows[scan['index']]=scan['count']
   if scan['axis']=='BOX':self.box[scan['id']]=scan['count']
   if scan['axis']=='SNIFF':
    if scan['dist'] is None:return 'STOP'
    self.sniff=(p,scan['dist'])
    for xx in range(w):
     for yy in range(h):
      if abs(xx-p[0])+abs(yy-p[1])==scan['dist'] and (xx,yy) not in vis:self.seen.discard((xx,yy))
  if level=='garden' and self.eaten==6:return 'STOP'
  # Dijkstra through currently observed body, avoiding collision; tail can be entered.
  occupied=set(body[1:-1]); dist={p:0}; first={}; heap=[(0,p)]
  while heap:
   d,q=heapq.heappop(heap)
   if d!=dist[q]:continue
   for dx,dy,a in [(1,0,'R'),(0,1,'D'),(-1,0,'L'),(0,-1,'U')]:
    z=(q[0]+dx,q[1]+dy)
    if not (0<=z[0]<w and 0<=z[1]<h) or z in occupied:continue
    if q==p and len(body)>2:
     blocked=set(body[:-1] if z not in self.food else body)
     if not any(0<=z[0]+ax<w and 0<=z[1]+ay<h and (z[0]+ax,z[1]+ay) not in blocked for ax,ay in ((1,0),(-1,0),(0,1),(0,-1))):continue
    nd=d+(o['rock_move_cost'] if z in self.rocks else 1)
    if nd<dist.get(z,99999):dist[z]=nd;first[z]=a if q==p else first[q];heapq.heappush(heap,(nd,z))
  food=[q for q in self.food if q in dist and q!=p]
  if food:
   target=min(food,key=lambda q:dist[q]);return first[target]
  if level in ('orchard','cellar') and o['large_wait']==0:
   options=[]
   for i,(x,y,side) in enumerate(self.windows):
    if i not in self.box:
     n=sum((xx,yy) not in self.seen and (xx,yy) not in self.rocks for xx in range(x,x+side) for yy in range(y,y+side))
     if n>=10:options.append((n/(3 if side<=7 else 5),i))
   if options:return 'BOX %d'%max(options)[1]
  if level=='marsh':
   if o.get('rustle'):self.sniff=None
   if o['large_wait']==0 and (self.sniff is None or o['steps']-self.sniff_step>=30):
    self.sniff_step=o['steps'];return 'SNIFF'
  # Avoid squares conclusively covered by zero-count queries.
  def uncertain(q):
   if q in self.seen or q in self.rocks:return False
   if level=='orchard' and self.rows.get(q[1],1)==0:return False
   for i,count in self.box.items():
    if count==0:
     x,y,s=self.windows[i]
     if x<=q[0]<x+s and y<=q[1]<y+s:return False
   return True
  candidates=[(x,y) for x in range(w) for y in range(h) if uncertain((x,y))]
  if level=='orchard' and not candidates and not self.food:return 'STOP'
  if level=='cellar' and not candidates and not self.food:return 'STOP'
  if level=='marsh' and self.sniff:
   origin,n=self.sniff; ring=[q for q in candidates if abs(q[0]-origin[0])+abs(q[1]-origin[1])==n]
   if ring:candidates=ring
  # Choose reachable vantage point covering many unknown cells, weighted for proximity.
  useful=set(candidates)
  if level=='orchard' and candidates:
   # Scan a promising row, then exploit zero rows.
   counts={y:sum((x,y) in useful for x in range(w)) for y in range(h) if y not in self.rows}
   if counts:
    yy=min(counts,key=lambda y:abs(y-p[1])-counts[y]*0.10)
    if abs(yy-p[1])<=2:return 'ROW %d'%yy
  best=None
  for q,d in dist.items():
   if q==p:continue
   gain=sum((xx,yy) in useful for xx in range(max(0,q[0]-radius),min(w,q[0]+radius+1)) for yy in range(max(0,q[1]-radius),min(h,q[1]+radius+1)) if abs(xx-q[0])+abs(yy-q[1])<=radius)
   if gain:
    score=(d+2.0)/(gain**0.75)
    if best is None or score<best[0]:best=(score,q)
  if best:return first[best[1]]
  if level=='marsh':
   if o['large_wait']==0:return 'SNIFF'
   opts=[q for q in dist if dist[q]==1 and q!=p]
   if opts:return first[opts[0]]
  # fallback safe move
  opts=[q for q in dist if q!=p]
  return first[min(opts,key=lambda q:dist[q])] if opts else 'STOP'

p=Player()
for line in sys.stdin:
 try: print(p.choose(json.loads(line)),flush=True)
 except Exception: print('STOP',flush=True)
