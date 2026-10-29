import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision import (ImageReader, RECTS, POINTS, WIDTH, HEIGHT,
                    norm_screen, point_to_screen, best_rotation)


class PortraitVisionTests(unittest.TestCase):
    def setUp(self):
        self.reader = ImageReader()

    def test_grid_is_portrait(self):
        self.assertEqual((WIDTH, HEIGHT), (900, 1600))
        self.assertLess(WIDTH, HEIGHT)

    def test_all_templates_exist_and_are_upright(self):
        self.assertEqual(set(self.reader.templates), set(RECTS))
        for name, (x1, y1, x2, y2) in RECTS.items():
            template = self.reader.templates[name]
            self.assertEqual(template.shape, (y2 - y1, x2 - x1), name)
            self.assertTrue(0 <= x1 < x2 <= WIDTH, name)
            self.assertTrue(0 <= y1 < y2 <= HEIGHT, name)

    def test_template_identity(self):
        for name, (x1, y1, x2, y2) in RECTS.items():
            template = self.reader.templates[name]
            frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            frame[y1:y2, x1:x2] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
            self.assertGreater(self.reader.score(frame, name), 0.98, name)

    def test_postbattle_ready_enabled_disabled(self):
        rect = RECTS['post_ready_enabled']
        for name, expected in [('post_ready_enabled', True), ('post_ready_disabled', False)]:
            template = self.reader.templates[name]
            frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            x1, y1, x2, y2 = rect
            frame[y1:y2, x1:x2] = cv2.cvtColor(template, cv2.COLOR_GRAY2BGR)
            for w, h in [(900, 1600), (571, 1013), (540, 960), (720, 1280)]:
                smaller = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
                scaled = cv2.resize(smaller, (WIDTH, HEIGHT), interpolation=cv2.INTER_LINEAR)
                self.assertIs(self.reader.post_ready_state(scaled), expected, (name, w, h))
        self.assertIsNone(self.reader.post_ready_state(np.zeros((HEIGHT, WIDTH, 3), np.uint8)))

    def test_auto_indicator_upright(self):
        img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        img[48:62, 562:576] = (255, 255, 255)
        self.assertIs(self.reader.auto_on(img), False)
        img[48:62, 562:576] = (5, 169, 255)
        self.assertIs(self.reader.auto_on(img), True)

    def test_click_mapping_for_portrait(self):
        x, y = POINTS['challenge']
        for rotation in range(4):
            area = (100, 200, WIDTH if rotation % 2 == 0 else HEIGHT,
                    HEIGHT if rotation % 2 == 0 else WIDTH)
            sx, sy = point_to_screen(x, y, area, rotation)
            self.assertTrue(area[0] <= sx <= area[0] + area[2])
            self.assertTrue(area[1] <= sy <= area[1] + area[3])
        self.assertAlmostEqual(point_to_screen(300, 200, (100, 200, 900, 1600), 0)[0],
                               400, delta=2)
        self.assertAlmostEqual(point_to_screen(300, 200, (100, 200, 1600, 900), 1)[0],
                               300, delta=2)

    def test_normalize_and_find_rotation(self):
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        tpl = self.reader.templates['challenge']
        x1, y1, x2, y2 = RECTS['challenge']
        frame[y1:y2, x1:x2] = cv2.cvtColor(tpl, cv2.COLOR_GRAY2BGR)
        for turns, reverse_code in [
                (0, None), (1, cv2.ROTATE_90_COUNTERCLOCKWISE),
                (2, cv2.ROTATE_180), (3, cv2.ROTATE_90_CLOCKWISE)]:
            raw = cv2.rotate(frame, reverse_code) if reverse_code is not None else frame
            restored = norm_screen(raw, turns)
            self.assertLess(float(np.mean(np.abs(restored.astype(int) - frame.astype(int)))), 0.2)
            guessed, normalized, score = best_rotation(raw, self.reader, 'Auto')
            self.assertEqual(guessed, turns)
            self.assertGreater(score, .98)


if __name__ == '__main__':
    unittest.main()
