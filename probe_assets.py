import cv2
from pathlib import Path
assets=Path(__file__).parent/'assets'; shots=Path('/mnt/data')
imgs={p.stem:cv2.imread(str(p),cv2.IMREAD_GRAYSCALE) for p in assets.glob('*.png')}
screens={
'home':'bbfff173-b427-4d1c-9424-32f6788c601f.png',
'select':'a935d5be-0ea7-452d-8415-c90e442d3441.png',
'ready':'db512dc1-d627-42be-be36-acdbefcf5fb1.png',
'auto':'1c33cce9-8490-4bf7-98c1-5e60db302f14.png',
'post':'2085bb08-4b21-4a32-a4d2-0203f725f01b.png',
'menu':'13a555e9-4a74-45d8-9327-50b07d490b00.png',
'retpop':'99b83c30-e7ad-448a-86b0-bbdf28fa838e.png',
'stampop':'ace51d67-8a1f-4384-8ce3-625cf248c6ff.png',
'res1':'27b810cd-7164-4eb3-8730-ef774fa89890.png',
'res2':'8cc79c63-633f-4eea-af08-0629c196f0ae.png',
'res3':'0b3fa6a6-29ed-44ab-8701-dd754c981acf.png',
'res4':'a1edeccd-9f7b-4332-9b87-376cbfed84e9.png',
}
# template origins from file
from make_assets import CROPS
coords={n:r for n,_,r in CROPS}
print(' '.join(f'{s:8}' for s in screens))
for name,t in imgs.items():
 l,top,right,b=coords[name];scores=[]
 for s,fn in screens.items():
  frame=cv2.imread(str(shots/fn),cv2.IMREAD_GRAYSCALE)
  box=frame[max(0,top-14):min(900,b+14),max(0,l-14):min(1600,right+14)]
  res=cv2.matchTemplate(box,t,cv2.TM_CCOEFF_NORMED)
  scores.append(float(res.max()))
 print(f'{name:20}', ' '.join(f'{v:.2f}' for v in scores))
