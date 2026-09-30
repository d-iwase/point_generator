from pathlib import Path
import sys
import tempfile
import threading
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generator import load_obj, point_count, generate, Cancelled


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.obj = self.root / "triangle.obj"
        self.obj.write_text("v 0 0 0\nv 2 0 0\nv 0 1 0\nf 1 2 3\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_progress_updates_inside_batch_and_load_stages(self):
        stages = []
        model = load_obj(self.obj, progress=lambda *values: stages.append(values))
        self.assertEqual(stages[0][0], 'OBJ読込')
        self.assertGreater(stages[0][1], 0)
        self.assertEqual(stages[-1], ('RGB・ラベルを準備中', None, None))
        updates = []
        generate(model, 25001, self.root / 'progress.txt', chunk_size=250000,
                 progress=lambda done, total: updates.append((done, total)))
        self.assertEqual(updates, [(10000, 25001), (20000, 25001), (25001, 25001)])

    def test_density_points_stay_on_surface(self):
        model = load_obj(self.obj)
        self.assertEqual(model.area, 1)
        self.assertEqual(point_count(model, 251), 251)
        progress = []
        output, count = generate(model, 251, self.root / "points.txt", seed=4, chunk_size=31,
                                  progress=lambda done, total: progress.append((done, total)))
        points = np.loadtxt(output)
        self.assertEqual(points.shape, (251, 3))
        np.testing.assert_array_equal(points[:, 2], 0)
        self.assertTrue((points >= 0).all())
        self.assertTrue((points[:, 0] / 2 + points[:, 1] <= 1 + 1e-8).all())
        self.assertEqual(progress[-1], (251, 251))
        self.assertLessEqual(max(np.diff([0] + [done for done, total in progress])), 31)
        self.assertNotIn("open3d", sys.modules)

    def test_polygon_negative_indices_and_bom(self):
        self.obj.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf -4/1 -3/2 -2/3 -1/4 # quad\n", encoding="utf-8-sig")
        model = load_obj(self.obj)
        self.assertEqual(model.area, 1)
        self.assertEqual(len(model.triangles), 2)

    def test_sampling_proportional_to_area(self):
        self.obj.write_text("v 0 0 0\nv 2 0 0\nv 0 1 0\nv 10 0 0\nv 18 0 0\nv 10 1 0\nf 1 2 3\nf 4 5 6\n")
        model = load_obj(self.obj)
        output, count = generate(model, 1000, self.root / "points.txt", seed=6)
        points = np.loadtxt(output)
        self.assertAlmostEqual(float((points[:, 0] >= 10).mean()), 0.8, delta=0.025)

    def test_cancellation_and_overwrite_protection(self):
        model = load_obj(self.obj)
        output = self.root / "cancel.txt"
        event = threading.Event()
        with self.assertRaises(Cancelled):
            generate(model, 100, output, chunk_size=20, cancel=event,
                     progress=lambda *_: event.set())
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob("*.partial")), [])
        output.write_text("keep")
        with self.assertRaises(FileExistsError):
            generate(model, 100, output)
        self.assertEqual(output.read_text(), "keep")

    def test_invalid_inputs(self):
        model = load_obj(self.obj)
        for density in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                point_count(model, density)
        for content in ("v 0 0 0\nf 1 1 1", "v nan 0 0\nf 1 1 1", "v 0 0 0\nf 0 1 1"):
            self.obj.write_text(content)
            with self.assertRaises(ValueError):
                load_obj(self.obj)

    def test_rgb_labels_stable_across_chunks_and_same_color_materials(self):
        self.obj.write_text("mtllib model colors.mtl\n"
            "v 0 0 0\nv 2 0 0\nv 0 1 0\n"
            "v 10 0 0\nv 12 0 0\nv 10 1 0\n"
            "v 20 0 0\nv 22 0 0\nv 20 1 0\n"
            "usemtl red\nf 1 2 3\nusemtl green\nf 4 5 6\nusemtl red_again\nf 7 8 9\n")
        (self.root / "model colors.mtl").write_text("newmtl red\nKd 1 0 0\nnewmtl green\nKd 0 1 0\nnewmtl red_again\nKd 1 0 0\n")
        model = load_obj(self.obj)
        self.assertEqual(model.missing_colors, 0)
        self.assertEqual(model.triangle_labels[0], model.triangle_labels[2])
        for batch in (17, 53):
            output, count = generate(model, 200, self.root / f"rgb{batch}.txt", chunk_size=batch,
                                      seed=5, use_rgb=True, use_labels=True)
            rows = np.loadtxt(output)
            self.assertEqual(rows.shape, (600, 7))
            green = (rows[:, 0] >= 10) & (rows[:, 0] < 20)
            np.testing.assert_array_equal(rows[green, 3:6], np.tile([0, 255, 0], (green.sum(), 1)))
            np.testing.assert_array_equal(rows[~green, 3:6], np.tile([255, 0, 0], ((~green).sum(), 1)))
            np.testing.assert_array_equal(rows[green, 6], model.triangle_labels[1])
            np.testing.assert_array_equal(rows[~green, 6], model.triangle_labels[0])

    def test_rgb_only_fallback_and_settings_validation(self):
        model = load_obj(self.obj)
        self.assertEqual(model.missing_colors, 1)
        output, _ = generate(model, 12, self.root / "rgb.txt", use_rgb=True)
        rows = np.loadtxt(output)
        self.assertEqual(rows.shape, (12, 6))
        np.testing.assert_array_equal(rows[:, 3:], 178)
        for batch in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                generate(model, 2, self.root / "invalid.txt", chunk_size=batch)
        with self.assertRaises(ValueError):
            generate(model, 2, self.root / "invalid.txt", use_labels=True)
        self.assertFalse((self.root / "invalid.txt").exists())


if __name__ == "__main__":
    unittest.main()
