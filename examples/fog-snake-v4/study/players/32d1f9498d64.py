import sys,json,heapq
class Player:
 def __init__(self):
  self.rocks=set(); self.possible=None; self.pending=False; self.last_scan_step=-100; self.last_eaten=0; self.visited={}; self.last_step=-1; self.covered=set(); self.route=None; self.idx=0
 def choose(self,o):
  w,h=o['size']; head=tuple(o['body'][0]); snake=list(map(tuple,o['body'])); food=set(map(tuple,o['food'])); step=o['steps']; universe={(x,y) for x in range(w) for y in range(h)}
  vis={head}|{(head[0]+dx,head[1]+dy) for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)) if 0<=head[0]+dx<w and 0<=head[1]+dy<h}
  self.rocks|=set(map(tuple,o['rocks'])); self.visited[head]=step; self.covered|=vis
  if self.route is None:
   columns=list(range(1,w,3))
   if columns[-1]<w-2:columns.append(w-1)
   self.route=[(x,y) for i,x in enumerate(columns) for y in (range(h) if i%2==0 else range(h-1,-1,-1))]
  while self.idx<len(self.route):
   x,y=self.route[self.idx]
   local={(x,y)}|{(x+dx,y+dy) for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)) if 0<=x+dx<w and 0<=y+dy<h}
   if local<=self.covered:self.idx+=1
   else:break

  if o['eaten']>self.last_eaten:self.possible=None; self.last_eaten=o['eaten']
  if self.possible is not None and step!=self.last_step:
   if o['rustle']:
    self.possible|={(x+dx,y+dy) for x,y in self.possible for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)) if 0<=x+dx<w and 0<=y+dy<h}
   self.possible-=vis-food; self.possible-=self.rocks
  self.last_step=step
  if self.pending:
   self.pending=False; scan=o.get('last_scan')
   if scan and scan['axis']=='SNIFF':
    d=scan['dist']
    if d is None:return 'STOP'
    ring={p for p in universe if abs(p[0]-head[0])+abs(p[1]-head[1])==d}-self.rocks-(vis-food)
    common=ring & self.possible if self.possible else set()
    self.possible=common if common else ring
  if not food and o['large_wait']==0 and (self.idx>=len(self.route) and step-self.last_scan_step>=24):
   self.pending=True; self.last_scan_step=step; return 'SNIFF'
  dirs=[(1,0,'R'),(0,1,'D'),(-1,0,'L'),(0,-1,'U')]
  def safe(q):
   grow=q in food
   if q in (snake if grow else snake[:-1]):return False
   b=[q]+(snake if grow else snake[:-1]); blocked=set(b[1:-1]); tail=b[-1]; stack=[q]; seen={q}
   while stack:
    p=stack.pop()
    if p==tail:return True
    for dx,dy,_ in dirs:
     z=(p[0]+dx,p[1]+dy)
     if 0<=z[0]<w and 0<=z[1]<h and z not in blocked and z not in seen:seen.add(z);stack.append(z)
   return False
  legal=[(head[0]+dx,head[1]+dy,a) for dx,dy,a in dirs if 0<=head[0]+dx<w and 0<=head[1]+dy<h and (head[0]+dx,head[1]+dy) not in snake[:-1]]
  moves=[t for t in legal if safe(t[:2])] or legal
  body=set(snake[1:-1]); dist={head:0}; first={}; heap=[]
  for x,y,a in moves:
   q=x,y; d=o['rock_move_cost'] if q in self.rocks else 1
   dist[q]=d;first[q]=a;heapq.heappush(heap,(d,q))
  while heap:
   d,p=heapq.heappop(heap)
   if d!=dist[p]:continue
   for dx,dy,a in dirs:
    q=p[0]+dx,p[1]+dy
    if not(0<=q[0]<w and 0<=q[1]<h) or q in body:continue
    nd=d+(o['rock_move_cost'] if q in self.rocks else 1)
    if nd<dist.get(q,1e9):dist[q]=nd;first[q]=first[p];heapq.heappush(heap,(nd,q))
  targets=[p for p in food if p in first]
  if targets:return first[min(targets,key=lambda p:dist[p])]
  if self.idx<len(self.route):
   p=self.route[self.idx]
   if p in first:return first[p]
  poss=self.possible or set()
  # Prefer steps revealing many positions on the current distance ring.
  best=None
  for p,d in dist.items():
   if p==head:continue
   gain=sum(q in poss for q in [p]+[(p[0]+dx,p[1]+dy) for dx,dy,_ in dirs])
   if gain:
    item=((d+1)/gain,d,p)
    if best is None or item<best:best=item
  if best:return first[best[2]]
  # If scan hypotheses are exhausted, move toward the least recently visited area.
  candidates=[p for p in first if p not in self.rocks]
  if candidates:
   target=min(candidates,key=lambda p:((max(0,step-self.visited.get(p,-100))**-.6)*(dist[p]+4),dist[p]))
   return first[target]
  return moves[0][2] if moves else 'STOP'
p=Player()
for line in sys.stdin:print(p.choose(json.loads(line)),flush=True)
