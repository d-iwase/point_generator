from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from test_ifc_conversion import make_ifc
from pipeline import run_pipeline
from generator import Cancelled


class PipelineTests(unittest.TestCase):
    def test_stage_times_are_measured_in_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'wall.obj'
            events = []
            with patch('pipeline.time.monotonic', side_effect=[10, 12, 15, 22]), \
                 patch('pipeline.convert_ifc', return_value=(output, output.with_suffix('.mtl'), (1, 8, 12))), \
                 patch('pipeline.load_obj'), patch('pipeline.generate', return_value=('cloud.txt', 280)):
                result = run_pipeline('wall.ifc', output, density=20, use_labels=False, event=lambda *item: events.append(item))
            self.assertEqual(result, ('cloud.txt', 280))
            self.assertEqual(events[-1], ('pipeline_timing', {
                'conversion': 2, 'preparation': 3, 'generation': 7, 'total': 12}))

    def test_existing_cloud_prevents_conversion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'wall.ifc'
            make_ifc(source)
            cloud = root / 'wall_surface.txt'
            cloud.write_text('keep')
            with self.assertRaises(FileExistsError):
                run_pipeline(source, root / 'wall.obj', density=20)
            self.assertFalse((root / 'wall.obj').exists())
            self.assertEqual(cloud.read_text(), 'keep')

    def test_cancel_after_conversion_keeps_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'wall.ifc'
            make_ifc(source)
            cancel = threading.Event()
            def event(kind, data):
                if kind == 'pipeline_converted':
                    cancel.set()
            with self.assertRaises(Cancelled):
                run_pipeline(source, root / 'wall.obj', density=20, cancel=cancel, event=event)
            self.assertTrue((root / 'wall.obj').exists())
            self.assertTrue((root / 'wall.mtl').exists())
            self.assertFalse((root / 'wall_surface.txt').exists())
