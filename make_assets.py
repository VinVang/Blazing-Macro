"""Maintainer utility: produce reference templates from screenshots supplied for this project.
Not needed to run the macro; assets/ already contains the extracted templates.
"""
from pathlib import Path
from PIL import Image

SRC=Path('/mnt/data')
OUT=Path(__file__).resolve().parent/'assets'
# Each entry: template name, developer source filename, old sideways crop.
# Saved templates are ROTATED CLOCKWISE to match portrait screen orientation.
CROPS=[
 ('challenge','bbfff173-b427-4d1c-9424-32f6788c601f.png',(1196,239,1370,665)),
 ('start_mission','a935d5be-0ea7-452d-8415-c90e442d3441.png',(1182,240,1344,654)),
 ('ready_initial','db512dc1-d627-42be-be36-acdbefcf5fb1.png',(1159,241,1253,663)),
 ('battle_menu','db512dc1-d627-42be-be36-acdbefcf5fb1.png',(25,25,82,183)),
 ('post_retreat','2085bb08-4b21-4a32-a4d2-0203f725f01b.png',(1157,458,1252,863)),
 ('post_ready_disabled','2085bb08-4b21-4a32-a4d2-0203f725f01b.png',(1160,37,1250,447)),
 ('post_ready_enabled','8c8b6ac1-2b48-4ba7-a582-13c77122151e.png',(1160,37,1250,447)),
 ('menu_title','13a555e9-4a74-45d8-9327-50b07d490b00.png',(149,179,243,711)),
 ('retreat_popup','99b83c30-e7ad-448a-86b0-bbdf28fa838e.png',(407,97,481,800)),
 ('stamina_popup','ace51d67-8a1f-4384-8ce3-625cf248c6ff.png',(507,102,597,805)),
 ('results_mission','27b810cd-7164-4eb3-8730-ef774fa89890.png',(278,139,375,801)),
 ('results_map','8cc79c63-633f-4eea-af08-0629c196f0ae.png',(282,160,355,753)),
 ('results_final','0b3fa6a6-29ed-44ab-8701-dd754c981acf.png',(647,59,759,853)),
 ('results_exp','a1edeccd-9f7b-4332-9b87-376cbfed84e9.png',(284,108,355,793)),
]
for name,filename,region in CROPS:
    Image.open(SRC/filename).crop(region).transpose(Image.Transpose.ROTATE_270).save(OUT/(name+'.png'), optimize=True)
print('saved',len(CROPS),'templates')
