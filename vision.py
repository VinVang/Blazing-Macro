"""Pure screen-image recognition for Naruto Road. No emulator or ADB API."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

WIDTH, HEIGHT = 900, 1600  # upright portrait reference grid
ASSETS = Path(__file__).resolve().parent / 'assets'

# Reference bounding boxes from user screenshots, rotated upright (900x1600).
# All template PNG files are upright portrait crops.
RECTS = {'challenge': (235, 1196, 661, 1370),
 'start_mission': (246, 1182, 660, 1344),
 'ready_initial': (237, 1159, 659, 1253),
 'battle_menu': (717, 25, 875, 82),
 'post_retreat': (37, 1157, 442, 1252),
 'post_ready_disabled': (453, 1160, 863, 1250),
 'post_ready_enabled': (453, 1160, 863, 1250),
 'menu_title': (189, 149, 721, 243),
 'retreat_popup': (100, 407, 803, 481),
 'stamina_popup': (95, 507, 798, 597),
 'results_mission': (99, 278, 761, 375),
 'results_map': (147, 282, 740, 355),
 'results_final': (47, 647, 841, 759),
 'results_exp': (83, 280, 250, 360)}

# Mouse targets in upright portrait reference coordinates.
POINTS = {'challenge': (459, 1269),
 'start': (448, 1255),
 'ready_initial': (444, 1211),
 'next_ready': (660, 1208),
 'post_retreat': (239, 1212),
 'menu_button': (798, 55),
 'menu_retreat': (259, 947),
 'retreat_yes': (633, 785),
 'stamina_no': (296, 1020),
 'auto_button': (624, 54),
 'ninjutsu': (178, 1413),
 'secret': (462, 1413),
 'latent': (748, 1413),
 'results_advance': (456, 1528),
 'results_middle': (455, 790)}

@dataclass(frozen=True)
class Match:
    name: str
    score: float


class ImageReader:
    def __init__(self, threshold: float = 0.80):
        self.threshold = threshold
        self.templates = {}
        for name in RECTS:
            raw = cv2.imread(str(ASSETS / (name + '.png')), cv2.IMREAD_GRAYSCALE)
            if raw is None:
                raise FileNotFoundError(f'Missing image template: {name}.png')
            self.templates[name] = raw

    def score(self, image: np.ndarray, name: str, margin: int = 16) -> float:
        x1,y1,x2,y2 = RECTS[name]
        tpl = self.templates[name]
        x1=max(0,x1-margin); x2=min(WIDTH,x2+margin)
        y1=max(0,y1-margin); y2=min(HEIGHT,y2+margin)
        roi = cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        if roi.shape[0] < tpl.shape[0] or roi.shape[1] < tpl.shape[1]:
            return 0.0
        score = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
        return float(np.max(score))

    def present(self, image: np.ndarray, name: str, threshold: float | None = None) -> bool:
        return self.score(image, name) >= (self.threshold if threshold is None else threshold)

    def identify(self, image: np.ndarray) -> Match:
        # Precedence matters: popups can have the underlying team's Start button.
        priority = ['stamina_popup','retreat_popup','menu_title',
                    'results_mission','results_map','results_final','results_exp',
                    'post_retreat','ready_initial','start_mission','challenge','battle_menu']
        for name in priority:
            score = self.score(image, name)
            if score >= self.threshold:
                return Match(name, score)
        highest = max((Match(n,self.score(image,n)) for n in priority), key=lambda item:item.score)
        return Match('unknown',highest.score)

    @staticmethod
    def indicator(image: np.ndarray, x: int, y: int) -> Optional[bool]:
        """Return True for a glowing gold dot, False for white, else None.

        Averages over a tiny central patch, avoiding surrounding decorative
        frame gold. Saturation alone can mistake a dark shadow for a selected
        dot, so also require orange hue and enough brightness.
        """
        if not (6 <= x < image.shape[1]-6 and 6 <= y < image.shape[0]-6):
            return None
        patch = image[y-5:y+6, x-5:x+6]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        hue, saturation, value = cv2.split(hsv)
        orange = ((hue >= 9) & (hue <= 36) &
                  (saturation >= 70) & (value >= 110))
        if float(np.mean(orange)) >= 0.23:
            return True
        if float(np.mean(value)) >= 65 and float(np.mean(saturation)) <= 42:
            return False
        return None

    def post_ready_state(self, image: np.ndarray) -> Optional[bool]:
        """After a map: True = Ready is clickable, False = gray/inactive.

        The two states share almost exactly the same lettering, so ordinary
        grayscale template matching alone is unsafe. Compare *both* reference
        states, then verify their very different text brightness. If the
        evidence disagrees (animation, popup, resized/cut-off game), don't click.
        """
        active = self.score(image, 'post_ready_enabled')
        inactive = self.score(image, 'post_ready_disabled')
        # Upright equivalent of the bright Ready lettering patch.
        letters = cv2.cvtColor(image[1182:1229,530:755], cv2.COLOR_BGR2GRAY)
        bright_fraction = float(np.mean(letters > 180))
        average_brightness = float(np.mean(letters))
        # Both supplied screenshots and 960p-to-2560p scaled copies are
        # separated by at least 0.09 in correlation and by ~65 gray levels.
        # Require agreement to avoid accidentally retreating on a won stage.
        if (active >= 0.78 and active-inactive >= 0.055
                and bright_fraction >= 0.16 and average_brightness >= 95):
            return True
        if (inactive >= 0.78 and inactive-active >= 0.055
                and bright_fraction <= 0.10 and average_brightness <= 90):
            return False
        return None

    def auto_on(self, image: np.ndarray) -> Optional[bool]:
        return self.indicator(image, 569, 55)

    def options_location(self, image: np.ndarray) -> Optional[tuple[int, int]]:
        """Find the AUTO PLAY menu via its left Ninjutsu button frame.

        The previous version used a broad, unstable panel fragment. In the
        user's live screenshot, battle animations obscure that fragment and
        the screen was classified 'unknown', even though Ninjutsu was visible.
        We now use the high-contrast Ninjutsu control itself, with margin for
        a slightly imperfect area selection. Works whether it is ON or OFF.
        Return the panel's displacement on the portrait reference grid.
        """
        x1, y1, x2, y2 = 32, 1369, 290, 1460
        pad = 32
        if not hasattr(self, '_options_anchor'):
            self._options_anchor = cv2.imread(
                str(ASSETS / 'auto_options_anchor.png'), cv2.IMREAD_GRAYSCALE)
        ref = self._options_anchor
        if ref is None:
            return None
        roi = cv2.cvtColor(
            image[y1-pad:y2+pad, max(0,x1-pad):x2+pad],
            cv2.COLOR_BGR2GRAY)
        if roi.shape[0] < ref.shape[0] or roi.shape[1] < ref.shape[1]:
            return None
        _, best, _, where = cv2.minMaxLoc(
            cv2.matchTemplate(roi, ref, cv2.TM_CCOEFF_NORMED))
        if best < 0.76:
            return None
        return where[0] - pad, where[1] - pad

    def options_visible(self, image: np.ndarray) -> bool:
        return self.options_location(image) is not None

    def option_state(self, image: np.ndarray, name: str) -> Optional[bool]:
        """Read button dots after locating the panel on the CURRENT frame.

        This is important if the selected emulator rectangle is a few pixels
        off relative to the original screenshots: the old fixed sampling
        coordinates included the dark background above the dot.
        """
        offset = self.options_location(image)
        if offset is None:
            return None
        dx, dy = offset
        x = {'ninjutsu':74, 'secret':367, 'latent':658}[name]
        return self.indicator(image, x + dx, 1416 + dy)


def norm_screen(frame: np.ndarray, rotation: int) -> np.ndarray:
    """Rotate a selected game area and resize to the upright 900x1600 grid.

    rotation indicates the number of 90-degree clockwise turns.
    """
    if rotation == 1: frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 2: frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation == 3: frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return cv2.resize(frame,(WIDTH,HEIGHT),interpolation=cv2.INTER_AREA if frame.shape[1]>WIDTH else cv2.INTER_LINEAR)


def point_to_screen(x: float, y: float, area: tuple[int,int,int,int], rotation: int) -> tuple[int,int]:
    """Invert the screenshot-to-normalized rotation mapping.

    area is (screen-left,screen-top,width,height) in physical pixels.
    """
    left,top,w,h = area
    nx = (x+0.5)/WIDTH
    ny = (y+0.5)/HEIGHT
    # Rotate raw clockwise `rotation` times to obtain normalized screenshot.
    if rotation == 0: rx,ry = nx,ny
    elif rotation == 1: rx,ry = ny,1-nx
    elif rotation == 2: rx,ry = 1-nx,1-ny
    else: rx,ry = 1-ny,nx
    return round(left+rx*w),round(top+ry*h)


def best_rotation(raw: np.ndarray, reader: ImageReader, requested: str) -> tuple[int, np.ndarray, float]:
    if requested != 'Auto':
        n={'0°':0,'90° clockwise':1,'180°':2,'90° counterclockwise':3}[requested]
        return n, norm_screen(raw,n), 1.0
    # A portrait game capture normally needs no rotation. Legacy landscape
    # captures still work; the two right-angle rotations are then evaluated.
    h,w=raw.shape[:2]
    candidates=(0,2) if h>=w else (1,3)
    top=(-1,None,None)
    for n in candidates:
        img=norm_screen(raw,n)
        confidence=max(reader.score(img,k) for k in
                       ('challenge','start_mission','ready_initial','battle_menu',
                        'results_map','results_exp','results_mission','stamina_popup'))
        if confidence>top[0]: top=(confidence,n,img)
    return top[1],top[2],top[0]


def _read_ocr(image: np.ndarray, pattern: str) -> str:
    """Read numeric HUD text; try multiple scales since the font is ornate.

    OCR is optional. On a machine without Tesseract the caller gets ''.
    Only trust strings matching the complete expected counter pattern.
    """
    try:
        import pytesseract
        import sys
        if sys.platform == 'win32':
            installed = Path('C:/Program Files/Tesseract-OCR/tesseract.exe')
            if installed.exists():
                pytesseract.pytesseract.tesseract_cmd = str(installed)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        for factor, psm in [(4, 7), (5, 7), (5, 8), (4, 8)]:
            enlarged = cv2.resize(gray, None, fx=factor, fy=factor,
                                  interpolation=cv2.INTER_NEAREST)
            detected = pytesseract.image_to_string(
                enlarged,
                config=f'--psm {psm} -c tessedit_char_whitelist=0123456789/').strip()
            if re.search(pattern, detected):
                return detected
    except Exception:
        pass
    return ''


def stamina_number(image: np.ndarray) -> Optional[int]:
    # Already upright; stamina lives on the upper-left HUD.
    # Crop tightly around the yellow stamina figures (not the entire gauge).
    field=image[130:160,139:270]
    value=_read_ocr(field, r'\d{1,3}\s*/\s*\d{2,4}')
    match=re.search(r'(\d{1,3})\s*/\s*(\d{2,4})',value)
    if not match: return None
    n,capacity=map(int,match.groups())
    return n if capacity>=20 and n<=capacity+100 else None


def map_number(image: np.ndarray) -> Optional[int]:
    field=image[8:52,208:369]
    value=_read_ocr(field, r'\d{1,2}\s*/\s*20')
    match=re.search(r'(\d{1,2})\s*/\s*20',value)
    if not match: return None
    n=int(match.group(1))
    return n if 1<=n<=20 else None
