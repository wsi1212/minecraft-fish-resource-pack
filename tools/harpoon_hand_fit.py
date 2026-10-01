#!/usr/bin/env python3
"""Preserve the prior harpoon size/grip and rotate the resting sprite upright around the grip viewing ray.

1.21.11 and 26.3 client ItemTransform/hand-renderer formulas were inspected locally.
Geometry projection is evidence, not an in-game screenshot. GUI and third person
remain owned by their existing models. No manual list of per-item Y offsets.
"""
import argparse,hashlib,json,math,os,io,zipfile
from pathlib import Path
from PIL import Image
RP=Path(os.environ.get('RP_ROOT',Path(__file__).resolve().parents[1]))
ASPECTS=[.625,2/3,1,4/3,16/9,32/9]
FOVS=[60,70,80]
FRAME=(.04,.30,.96,.88) # previous resting head frame
ROTATIONS={'firstperson_righthand':[15,115,-45],'firstperson_lefthand':[15,115,-135]}
MAX_SCALE=1.25
DEPTH_RATIO=.125 # generated 1/16 depth overwhelms detailed, thin spear artwork
CAM_COM=(.28,-.17,-1.45) # prior resting pose; keep its size/position
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

def native_raise(point,progress,left):
 """Vanilla 1.21.11 SpearAnimations.firstPersonUse, initial raise phase.
 Includes both pivot rotations, three raise subphases and inOutBack easing.
 No component/material override: the native spear still controls combat.
 """
 h=-1 if left else 1
 ramp=lambda lo,hi:max(0,min(1,(progress-lo)/(hi-lo)))
 start=ramp(0,.5);middle=ramp(.5,.8);end=ramp(.8,1)
 c=1.70158*1.525
 ease=((2*progress)**2*((c+1)*2*progress-c))/2 if progress<.5 else ((2*progress-2)**2*((c+1)*(progress*2-2)+c)+2)/2
 yaw=90*ramp(.5,.55)
 p=rotate((point[0]-h*.15,point[1],point[2]),[0,h*yaw,0]);p=(p[0]+h*.15,p[1]-.1,p[2]);p=rotate(p,[-65*ease,0,0]);p=(p[0],p[1]+.1,p[2])
 return (p[0]+h*(.15*progress-.05*end),p[1]-.075*progress+.075*middle,p[2]+.05*start-.05*end)

def inverse_raised(point,left):
 h=-1 if left else 1
 p=(point[0]-h*.1,point[1]-.1,point[2]);p=rotate(p,[65,0,0]);p=(p[0]-h*.15,p[1]+.1,p[2]);p=rotate(p,[0,-h*90,0]);return(p[0]+h*.15,p[1],p[2])

def xyz_from_basis(columns):
 # ItemTransform uses quaternion.rotationXYZ: R = Rx Ry Rz.
 m=[[columns[j][i]for j in range(3)]for i in range(3)]
 return [math.degrees(math.atan2(-m[1][2],m[2][2])),math.degrees(math.asin(max(-1,min(1,m[0][2])))),math.degrees(math.atan2(-m[0][1],m[0][0]))]

def fit_original(center,points,context,landmarks=None):
 left=context.endswith('lefthand')
 if landmarks is None:raise ValueError('alpha-weighted spear landmarks are required')
 angle=landmarks['angle'];rawrot=[15,115,angle-180 if left else -angle];rot=(rawrot[0],-rawrot[1]if left else rawrot[1],-rawrot[2]if left else rawrot[2]);com=rotate(landmarks['head'],rot)
 axis=landmarks['axis'];headpoints=[p for p in points if p[0]*axis[0]+p[1]*axis[1]>=landmarks['cut']]
 thin=lambda p:(p[0],p[1],p[2]*DEPTH_RATIO)
 rotated=[rotate(thin(p),rot)for p in headpoints];deltas=[tuple(p[k]-com[k]for k in range(3))for p in rotated]
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
  dz=rotate(thin(p),rot)[2]-com[2]
  if dz>0:scale=min(scale,(depth-.12)/dz)
 scale=round(scale*.998,6);base=(-.56 if left else .56,-.52,-.72)
 tr=[16*(target[k]-base[k]-scale*com[k])for k in range(3)]
 if left:tr[0]*=-1
 pose=dict(rotation=[round(v,6)for v in rawrot],translation=[round(v,6)for v in tr],scale=[scale,scale,round(scale*DEPTH_RATIO,6)])
 cams=camera_points(points,pose,left);headcams=camera_points(headpoints,pose,left);frames=[]
 for aspect in ASPECTS:
  for fov in FOVS:
   screen=[project(p,aspect,fov)for p in cams];box=[min(x for x,y in screen),min(y for x,y in screen),max(x for x,y in screen),max(y for x,y in screen)]
   hs=[project(p,aspect,fov)for p in headcams];hb=[min(x for x,y in hs),min(y for x,y in hs),max(x for x,y in hs),max(y for x,y in hs)]
   fits=hb[0]>=FRAME[0]and hb[1]>=FRAME[1]and hb[2]<=FRAME[2]and hb[3]<=FRAME[3]and all(p[2]<-.05 for p in cams)
   if not fits:raise ValueError((context,aspect,fov,hb))
   frames.append(dict(aspect=aspect,fov=fov,bounds=box,head_bounds=hb,grip=project(camera_points([landmarks['grip']],pose,left)[0],aspect,fov)))
 return pose,frames

def upright_pose(pose,landmarks,context,degrees=30):
 """Rotate around the grip viewing ray; preserve its camera position and scale.

 Camera Z is incorrect for an off-axis grip with perspective depth: it moves
 the head sideways while barely changing the visible shaft angle. A rigid
 Rodrigues rotation around the grip ray keeps the lower-right hand anchored
 and changes the visible resting angle without shrinking the model.
 """
 left=context.endswith('lefthand')
 rot,tr=effective(pose,left)
 grip=tuple(landmarks['grip'][k]*pose['scale'][k]for k in range(3))
 pivot=rotate(grip,rot)
 cam=camera_points([landmarks['grip']],pose,left)[0]
 norm=math.sqrt(sum(v*v for v in cam))
 if norm<1e-8:raise ValueError('grip must be outside the camera origin')
 axis=tuple(v/norm for v in cam)
 ang=math.radians(-degrees if left else degrees)
 def turn(p):
  cross=(axis[1]*p[2]-axis[2]*p[1],axis[2]*p[0]-axis[0]*p[2],axis[0]*p[1]-axis[1]*p[0]);dot=sum(axis[k]*p[k]for k in range(3));return tuple(p[k]*math.cos(ang)+cross[k]*math.sin(ang)+axis[k]*dot*(1-math.cos(ang))for k in range(3))
 basis=[turn(rotate(v,rot))for v in [(1,0,0),(0,1,0),(0,0,1)]];newrot=xyz_from_basis(basis);newpivot=rotate(grip,newrot);translated=[16*(tr[k]+pivot[k]-newpivot[k])for k in range(3)]
 if left:translated[0]*=-1
 return {'rotation':[round(newrot[0],6),round(-newrot[1]if left else newrot[1],6),round(-newrot[2]if left else newrot[2],6)],'translation':[round(v,6)for v in translated],'scale':list(pose['scale'])}
def fit(center,points,context,landmarks=None):
 pose,frames=fit_original(center,points,context,landmarks)
 return upright_pose(pose,landmarks,context),frames

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');ap.add_argument('--inventory',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);ap.add_argument('--texture-pack',type=Path,help='Calibrate the actual published texture bytes, including retained downscaled sprites');ap.add_argument('--baseline-pack',type=Path,help='Restore exact previous first-person size/position, then only rotate around its grip');ap.add_argument('--upright-degrees',type=float,default=30);args=ap.parse_args()
 texture_pack=zipfile.ZipFile(args.texture_pack)if args.texture_pack else None
 baseline_pack=zipfile.ZipFile(args.baseline_pack)if args.baseline_pack else None
 inv=json.loads(args.inventory.read_text());rows=[r for r in inv['equipment']if r['kind']=='작살'];report=[];changed=0
 for r in rows:
  path=RP/r['local']['model'];texture=RP/r['local']['texture'];model=json.loads(path.read_text());before=json.loads(json.dumps(model));texture_bytes=texture_pack.read(r['local']['texture'])if texture_pack else texture.read_bytes();im=Image.open(io.BytesIO(texture_bytes));center,points=geometry(im);landmarks=spear_landmarks(im);details={}
  # Exact generated sprite geometry only; fail closed for future true 3D tools.
  if 'elements'in model:raise ValueError('3D geometry requires separate calibration: '+str(path))
  for context in ROTATIONS:
   
   if baseline_pack:
    oldpose=json.loads(baseline_pack.read(r['local']['model']))['display'][context]
    pose=upright_pose(oldpose,landmarks,context,args.upright_degrees);frames=[]
    beforegrip=camera_points([landmarks['grip']],oldpose,context.endswith('lefthand'))[0];aftergrip=camera_points([landmarks['grip']],pose,context.endswith('lefthand'))[0]
    assert pose['scale']==oldpose['scale'] and max(abs(a-b)for a,b in zip(beforegrip,aftergrip))<1e-6
   else:pose,frames=fit(center,points,context,landmarks)
   model.setdefault('display',{})[context]=pose;details[context]=dict(pose=pose,frames=frames)
  if model!=before:
   changed+=1
   if args.apply:
    backup=args.report.parent/'before-models'/r['local']['model']
    if not backup.exists():backup.parent.mkdir(parents=True,exist_ok=True);backup.write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n')
    path.write_text(json.dumps(model,ensure_ascii=False,indent=2)+'\n')
  report.append(dict(id=r.get('id',r.get('key')),name=r['name'],model=r['local']['model'],texture=r['local']['texture'],texture_sha256=hashlib.sha256(texture_bytes).hexdigest(),local_texture_sha256=hashlib.sha256(texture.read_bytes()).hexdigest(),changed=model!=before,center=center,landmarks=landmarks,contexts=details))
 args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(dict(count=len(rows),changed=changed,aspects=ASPECTS,fovs=FOVS,frame=FRAME,scope='previous resting size/grip restored, grip viewing-ray rotation; camera-Z roll and native inverse raise superseded',items=report),ensure_ascii=False,indent=2)+'\n')
 if baseline_pack:print('Restored',len(rows),'harpoons;',changed,'changes; scale/thickness and camera grip preserved; viewing-ray rotation',args.upright_degrees,'degrees')
 else:print('Projected',len(rows),'harpoons;',changed,'model changes; upright grip rotation applied')
if __name__=='__main__':main()
