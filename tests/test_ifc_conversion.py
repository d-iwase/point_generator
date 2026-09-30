from pathlib import Path
import sys, tempfile, threading, unittest
import numpy as np
import ifcopenshell.api
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ifc_conversion import convert_ifc
from generator import load_obj, Cancelled

def make_ifc(path, millimetres=False, rotate=False):
    run = ifcopenshell.api.run
    model = run("project.create_file")
    run("root.create_entity", model, ifc_class="IfcProject", name="IFC load test")
    length = run("unit.add_si_unit", model, unit_type="LENGTHUNIT", prefix="MILLI" if millimetres else None)
    run("unit.assign_unit", model, units=[length])
    context = run("context.add_context", model, context_type="Model")
    body = run("context.add_context", model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context)
    wall = run("root.create_entity", model, ifc_class="IfcWall", name="Wall")
    representation = run("geometry.add_wall_representation", model, context=body, length=2, height=3, thickness=0.2)
    run("geometry.assign_representation", model, product=wall, representation=representation)
    matrix = np.eye(4)
    if rotate:
        angle = np.deg2rad(33)
        matrix[:2, :2] = [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    matrix[:3, 3] = [10, 20, 30]
    run("geometry.edit_object_placement", model, product=wall, matrix=matrix)
    style = run("style.add_style", model, name="Red wall")
    run("style.add_surface_style", model, style=style, ifc_class="IfcSurfaceStyleShading",
        attributes={"SurfaceColour": {"Name": None, "Red": 1.0, "Green": 0.0, "Blue": 0.0}})
    run("style.assign_representation_styles", model, shape_representation=representation, styles=[style])
    model.write(str(path))


class ConversionTests(unittest.TestCase):
    def test_conversion_options_and_colors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for mm in (False, True):
                source = root / f"wall{mm}.ifc"
                make_ifc(source, mm, rotate=True)
                before = source.read_bytes()
                for scaled, keep in ((True, False), (False, True)):
                    output = root / f"actual{mm}{scaled}" / "model.obj"
                    obj, mtl, counts = convert_ifc(source, output, use_mm_scale=scaled, keep_direction=keep)
                    self.assertTrue(obj.is_file())
                    self.assertTrue(mtl.is_file())
                    self.assertIn(f"mtllib {mtl.name}", obj.read_text(encoding="utf-8"))
                    model = load_obj(obj)
                    self.assertAlmostEqual(model.area, 14e-6 if scaled else 14, places=5)
                    np.testing.assert_array_equal(model.triangle_rgb, np.tile([255, 0, 0], (len(model.triangles), 1)))
                    self.assertGreater(counts[0], 0)
                self.assertEqual(source.read_bytes(), before)

    def test_names_protection_and_cancellation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'wall.ifc'
            make_ifc(source)
            target = root / 'converted model.obj'
            obj, mtl, _ = convert_ifc(source, target)
            self.assertIn('mtllib converted model.mtl', obj.read_text(encoding='utf-8'))
            self.assertEqual(load_obj(obj).missing_colors, 0)
            with self.assertRaises(FileExistsError):
                convert_ifc(source, target)
            protected = root / 'protected.mtl'
            protected.write_text('keep')
            with self.assertRaises(FileExistsError):
                convert_ifc(source, protected.with_suffix('.obj'))
            self.assertEqual(protected.read_text(), 'keep')
            before = set(root.iterdir())
            event = threading.Event()
            with self.assertRaises(Cancelled):
                convert_ifc(source, root / 'cancelled.obj', cancel=event, progress=lambda _: event.set())
            self.assertEqual(set(root.iterdir()), before)

if __name__ == '__main__':
    unittest.main()
