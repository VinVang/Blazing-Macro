"""Regression tests for the real AUTO PLAY state in captured battle frames.

The fixtures are bottom-panel crops only; they contain no user's desktop.
"""
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vision import ImageReader, WIDTH, HEIGHT
from runner import NinjaRoadRunner


class AutoPanelRegressionTests(unittest.TestCase):
    def setUp(self):
        self.reader=ImageReader()

    @staticmethod
    def frame(state):
        panel=cv2.imread(str(ROOT/'tests'/'fixtures'/f'auto_panel_{state}.png'))
        assert panel is not None
        image=np.zeros((HEIGHT, WIDTH, 3),dtype=np.uint8)
        image[1280:1600,:,:]=panel
        return image

    def test_detect_live_panel_even_when_top_menu_obscured(self):
        frame=self.frame('off')
        self.assertTrue(self.reader.options_visible(frame))
        self.assertFalse(self.reader.option_state(frame,'ninjutsu'))
        self.assertFalse(self.reader.option_state(frame,'secret'))
        self.assertFalse(self.reader.option_state(frame,'latent'))

    def test_detect_highlighted_ninjutsu_and_leave_it(self):
        frame=self.frame('on')
        self.assertTrue(self.reader.options_visible(frame))
        self.assertTrue(self.reader.option_state(frame,'ninjutsu'))
        self.assertFalse(self.reader.option_state(frame,'secret'))
        self.assertFalse(self.reader.option_state(frame,'latent'))

    def test_detect_at_different_emulator_sizes(self):
        for state, expected in [('off',False),('on',True)]:
            base=self.frame(state)
            for w,h in [(571,1013),(540,960),(720,1280),(1080,1920)]:
                with self.subTest(state=state,width=w,height=h):
                    shrunk=cv2.resize(base,(w,h),interpolation=cv2.INTER_AREA if w<900 else cv2.INTER_LINEAR)
                    restored=cv2.resize(shrunk,(WIDTH,HEIGHT),interpolation=cv2.INTER_LINEAR)
                    self.assertTrue(self.reader.options_visible(restored))
                    self.assertIs(self.reader.option_state(restored,'ninjutsu'),expected)

    def test_runner_clicks_ninjutsu_only_when_unselected(self):
        actions=[]
        bot=NinjaRoadRunner((0,0,900,1600),'0°',False,0,.8,0,
                            lambda *_:None)
        bot._click=lambda name,delay=None:actions.append(name) or True
        self.assertTrue(bot._maybe_configure_auto(self.frame('off')))
        self.assertEqual(actions,['ninjutsu'])
        actions.clear()
        # New runner to avoid any elapsed-time/throttle behavior.
        bot2=NinjaRoadRunner((0,0,900,1600),'0°',False,0,.8,0,
                            lambda *_:None)
        bot2._click=lambda name,delay=None:actions.append(name) or True
        self.assertFalse(bot2._maybe_configure_auto(self.frame('on')))
        self.assertEqual(actions,[])

    def test_no_phantom_panel_on_initial_ready_screen(self):
        frame=np.zeros((HEIGHT, WIDTH, 3),dtype=np.uint8)
        self.assertFalse(self.reader.options_visible(frame))
        self.assertIsNone(self.reader.option_state(frame,'ninjutsu'))


if __name__=='__main__':
    unittest.main()
