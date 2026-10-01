#!/usr/bin/env python3
"""Calibrate generated harpoon sprites in the actual idle hand camera frame.

1.21.11 and 26.3 client ItemTransform/hand-renderer formulas were inspected locally.
Geometry projection is evidence, not an in-game screenshot. GUI and third person
remain owned by their existing models. No manual list of per-item Y offsets.
"""
import argparse,hashlib,json,math,os
from pathlib import Path
from PIL import Image
RP=Path(os.environ.get('RP_ROOT',Path(__file__).resolve().parents[1]))
ASPECTS=[.625,2/3,1,4/3,16/9,32/9]
FOVS=[60,70,80]
FRAME=(.04,.30,.96,.88) # safe head region; the shaft continues toward the hand
ROTATIONS={'firstperson_righthand':[15,115,-45],'firstperson_lefthand':[15,115,-135]}
MAX_SCALE=1.25
CAM_COM=(.28,-.17,-1.45) # head anchor, not the whole item's mass center
def rotate(point,rotation):
 x,y,z=point;rx,ry,rz=map(math.radians,rotation)
 x,y=x*math.cos(rz)-y*math.sin(rz),x*math.sin(rz)+y*math.cos(rz)
 x,z=x*math.cos(ry)+z*math.sin(ry),-x*math.sin(ry)+z*math.cos(ry)
 y,z=y*math.cos(rx)-z*math.sin(rx),y*math.sin(rx)+z*math.cos(rx)
 return x,y,z

def geometry(im):
 im=im.convert('RGBA');w,h=im.size;alpha=list(im.getchannel('A').get_flattened_data());mass=sum(alpha)
 if w!=h:raise ValueError('animation strips require per-frame calibration')
 if not mass:raise ValueError('fully transparent sprite')
 center=(sum((i%w+.5)*a for i,a in enumerate(alpha))/mass/w-.5,.5-sum((i//w+.5)*a for i,a in enumerate(alpha))/mass/h,0)
 points=set()
 for yy in range(h):
  visible=[xx for xx in range(w)if alpha[yy*w+xx]>0]
  if not visible:continue
  # Row envelope contains every visible pixel corner, and generated depth is 1/16.
  for xx in [min(visible),max(visible)+1]:
   for y in [yy,yy+1]:
    for z in [-1/32,1/32]:points.add((xx/w-.5,.5-y/h,z))
 return center,list(points)

def spear_landmarks(im):
 """Alpha-weighted shaft direction and head mass; artwork points upper-right.

 Fit the spear head to the aiming area, rather than floating the whole spear in
 the middle of the screen. Its grip/shaft are allowed to exit at the hand edge.
 """
 im=im.convert('RGBA');w,h=im.size;pixels=[]
 for yy in range(h):
  for xx in range(w):
   a=im.getpixel((xx,yy))[3]
   if a:pixels.append((xx/w-.5,.5-yy/h,a))
 mass=sum(a for x,y,a in pixels);cx=sum(x*a for x,y,a in pixels)/mass;cy=sum(y*a for x,y,a in pixels)/mass
 xx=sum(a*(x-cx)**2 for x,y,a in pixels)/mass;yy=sum(a*(y-cy)**2 for x,y,a in pixels)/mass;xy=sum(a*(x-cx)*(y-cy)for x,y,a in pixels)/mass
 theta=.5*math.atan2(2*xy,xx-yy);axis=(math.cos(theta),math.sin(theta))
 if not (axis[0]>0 and axis[1]>0):raise ValueError('artwork must have its spearhead upper-right')
 ts=[x*axis[0]+y*axis[1]for x,y,a in pixels];lo=min(ts);hi=max(ts);cut=lo+.68*(hi-lo)
 head=[(x,y,a)for x,y,a in pixels if x*axis[0]+y*axis[1]>=cut];hm=sum(a for x,y,a in head)
 grip=[(x,y,a)for x,y,a in pixels if lo+.12*(hi-lo)<=x*axis[0]+y*axis[1]<=lo+.28*(hi-lo)];gm=sum(a for x,y,a in grip)
 return dict(angle=math.degrees(theta),axis=axis,head=[sum(x*a for x,y,a in head)/hm,sum(y*a for x,y,a in head)/hm,0],grip=[sum(x*a for x,y,a in grip)/gm,sum(y*a for x,y,a in grip)/gm,0],cut=cut)

def effective(pose,left):
 rot=pose['rotation'];tr=pose['translation'];return (rot[0],-rot[1]if left else rot[1],-rot[2]if left else rot[2]),((-tr[0]if left else tr[0])/16,tr[1]/16,tr[2]/16)

def camera_points(points,pose,left):
 rotation,tr=effective(pose,left);base=(-.56 if left else .56,-.52,-.72);sc=pose['scale']
 return [tuple(base[k]+tr[k]+rotate(tuple(p[k]*sc[k]for k in range(3)),rotation)[k]for k in range(3))for p in points]

def project(p,aspect,fov):
 x,y,z=p;f=1/math.tan(math.radians(fov)/2)
 return ((1+x*f/aspect/-z)/2,(1-y*f/-z)/2)

def fit(center,points,context,landmarks=None):
 left=context.endswith('lefthand')
 if landmarks is None:raise ValueError('alpha-weighted spear landmarks are required')
 angle=landmarks['angle'];rawrot=[15,115,angle-180 if left else -angle];rot=(rawrot[0],-rawrot[1]if left else rawrot[1],-rawrot[2]if left else rawrot[2]);com=rotate(landmarks['head'],rot)
 axis=landmarks['axis'];headpoints=[p for p in points if p[0]*axis[0]+p[1]*axis[1]>=landmarks['cut']]
 rotated=[rotate(p,rot)for p in headpoints];deltas=[tuple(p[k]-com[k]for k in range(3))for p in rotated]
 target=((-1 if left else 1)*CAM_COM[0],CAM_COM[1],CAM_COM[2]);depth=-target[2];scale=MAX_SCALE
 # Solve every head frustum half-space. Whole-item centering is deliberately
 # avoided: native spears extend from the right/left hand into the aiming area.
 lo_x=2*FRAME[0]-1;hi_x=2*FRAME[2]-1;lo_y=1-2*FRAME[3];hi_y=1-2*FRAME[1]
 for aspect in ASPECTS:
  for fov in FOVS:
   f=1/math.tan(math.radians(fov)/2)
   for dx,dy,dz in deltas:
    for coefficient,limit in [(f/aspect*dx+hi_x*dz,hi_x*depth-f/aspect*target[0]),(-f/aspect*dx-lo_x*dz,f/aspect*target[0]-lo_x*depth),(f*dy+hi_y*dz,hi_y*depth-f*target[1]),(-f*dy-lo_y*dz,f*target[1]-lo_y*depth),(dz,depth-.05)]:
     if limit<0:raise ValueError('target outside calibration frame')
     if coefficient>0:scale=min(scale,limit/coefficient)
 for p in points:
  dz=rotate(p,rot)[2]-com[2]
  if dz>0:scale=min(scale,(depth-.12)/dz)
 scale=round(scale*.998,6);base=(-.56 if left else .56,-.52,-.72)
 tr=[16*(target[k]-base[k]-scale*com[k])for k in range(3)]
 if left:tr[0]*=-1
 pose=dict(rotation=[round(v,6)for v in rawrot],translation=[round(v,6)for v in tr],scale=[scale]*3)
 cams=camera_points(points,pose,left);headcams=camera_points(headpoints,pose,left);frames=[]
 for aspect in ASPECTS:
  for fov in FOVS:
   screen=[project(p,aspect,fov)for p in cams];box=[min(x for x,y in screen),min(y for x,y in screen),max(x for x,y in screen),max(y for x,y in screen)]
   hs=[project(p,aspect,fov)for p in headcams];hb=[min(x for x,y in hs),min(y for x,y in hs),max(x for x,y in hs),max(y for x,y in hs)]
   fits=hb[0]>=FRAME[0]and hb[1]>=FRAME[1]and hb[2]<=FRAME[2]and hb[3]<=FRAME[3]and all(p[2]<-.05 for p in cams)
   if not fits:raise ValueError((context,aspect,fov,hb))
   frames.append(dict(aspect=aspect,fov=fov,bounds=box,head_bounds=hb,grip=project(camera_points([landmarks['grip']],pose,left)[0],aspect,fov)))
 return pose,frames

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);args=ap.parse_args()
 inv=json.loads(args.inventory.read_text());rows=[r for r in inv['equipment']if r['kind']=='작살'];report=[];changed=0
 for r in rows:
  path=RP/r['local']['model'];texture=RP/r['local']['texture'];model=json.loads(path.read_text());before=json.loads(json.dumps(model));im=Image.open(texture);center,points=geometry(im);landmarks=spear_landmarks(im);details={}
  # Exact generated sprite geometry only; fail closed for future true 3D tools.
  if 'elements'in model:raise ValueError('3D geometry requires separate calibration: '+str(path))
  for context in ROTATIONS:
   pose,frames=fit(center,points,context,landmarks);model.setdefault('display',{})[context]=pose;details[context]=dict(pose=pose,frames=frames)
  if model!=before:
   changed+=1
   if args.apply:
    backup=args.report.parent/'before-models'/r['local']['model']
    if not backup.exists():backup.parent.mkdir(parents=True,exist_ok=True);backup.write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n')
    path.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
  report.append(dict(id=r.get('id',r.get('key')),name=r['name'],model=r['local']['model'],texture=r['local']['texture'],texture_sha256=hashlib.sha256(texture.read_bytes()).hexdigest(),center=center,landmarks=landmarks,contexts=details))
 args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(dict(count=len(rows),changed=changed,aspects=ASPECTS,fovs=FOVS,frame=FRAME,scope='idle/equipped sprite; no swing, swap, damage bob or third-person proof',items=report),ensure_ascii=False,indent=2)+'\n')
 print('Projected',len(rows),'harpoons;',changed,'model changes;',len(rows)*2*len(ASPECTS)*len(FOVS),'hand/aspect/FOV combinations')
if __name__=='__main__':main()
