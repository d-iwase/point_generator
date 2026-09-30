from pathlib import Path
import sys
import csv
import tempfile
import time
import tkinter as tk
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Application
from test_ifc_conversion import make_ifc


def wait(root, app):
    deadline = time.monotonic() + 30
    while app.busy:
        root.update()
        if time.monotonic() > deadline:
            raise TimeoutError('Worker did not finish')
        time.sleep(.01)
    root.update()


with tempfile.TemporaryDirectory() as folder:
    folder = Path(folder)
    source = folder / 'wall.ifc'
    make_ifc(source)
    root = tk.Tk()
    app = Application(root)
    try:
        root.update()
        assert app.mm_scale.get() and not app.keep_direction.get()
        with patch('app.filedialog.askopenfilename', return_value=str(source)):
            app.ifc_open_button.invoke()
        app.mm_scale.set(False)
        output = folder / 'wall model.obj'
        with patch('app.filedialog.asksaveasfilename', return_value=str(output)):
            app.ifc_convert_button.invoke()
        assert app.busy
        assert str(app.open_button['state']) == 'disabled'
        wait(root, app)
        assert output.exists() and output.with_suffix('.mtl').exists()
        assert app.model is None and not list(folder.glob('*.txt'))
        app.use_converted_button.invoke()
        wait(root, app)
        assert app.notebook.select() == str(app.point_tab)
        assert app.model is not None and app.model.missing_colors == 0
        assert not list(folder.glob('*.txt'))
        app.density.set('20')
        app.start_generation(folder / 'cloud.txt')
        wait(root, app)
        points = np.loadtxt(folder / 'cloud.txt')
        assert points.shape == (280, 7)
        np.testing.assert_array_equal(points[:, 3:6], np.tile([255, 0, 0], (280, 1)))
        assert 'open3d' not in sys.modules
        combined = folder / 'combined.obj'
        with patch('app.filedialog.askopenfilename', return_value=str(source)), patch('app.filedialog.asksaveasfilename', return_value=str(combined)):
            app.pipeline_button.invoke()
        assert app.busy
        assert str(app.pipeline_button['state']) == 'disabled'
        wait(root, app)
        assert combined.exists() and combined.with_suffix('.mtl').exists()
        cloud = folder / 'combined_surface.txt'
        combined_points = np.loadtxt(cloud)
        assert combined_points.shape == (280, 7)
        np.testing.assert_array_equal(combined_points[:, 3:6], np.tile([255, 0, 0], (280, 1)))
        assert app.last_output == cloud
        mapping = folder / 'combined_labels.csv'
        with mapping.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 1
        assert rows[0]['ifc_class'] == 'IfcWall'
        assert rows[0]['member_count'] == '1'
        assert int(rows[0]['label']) == int(combined_points[0, 6])
        assert [int(rows[0][key]) for key in ('R', 'G', 'B')] == [255, 0, 0]
        assert str(mapping) in app.output_text.get()
        assert '合計' in app.timing.get()
        assert 'IFC → OBJ・MTL変換:' in app.timing.get()
        assert 'OBJ読込・点群準備:' in app.timing.get()
        assert '点群生成・TXT保存:' in app.timing.get()
        durations = app.pipeline_timing
        assert abs(durations['total'] - sum(durations[key] for key in ('conversion', 'preparation', 'generation'))) < 1e-6
        assert not app.busy
        print('PASS: one-click IFC pipeline, shared settings, RGB/labels and three outputs')
        print('PASS: IFC conversion, explicit OBJ handoff, RGB/label cloud, no automatic generation')
    finally:
        root.destroy()
