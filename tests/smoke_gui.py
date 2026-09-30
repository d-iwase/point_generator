from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Application
from generator import generate


def wait(root, app):
    deadline = time.monotonic() + 20
    while app.busy:
        root.update()
        if time.monotonic() > deadline:
            raise TimeoutError("Worker did not finish")
        time.sleep(0.01)
    root.update()


with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    obj = folder / "triangle.obj"
    obj.write_text("mtllib triangle.mtl\nv 0 0 0\nv 2 0 0\nv 0 1 0\nusemtl red\nf 1 2 3\n")
    obj.with_suffix(".mtl").write_text("newmtl red\nKd 1 0 0\n")
    root = tk.Tk()
    app = Application(root)
    try:
        root.update()
        with patch("app.filedialog.askopenfilename", return_value=str(obj)):
            app.open_button.invoke()
        wait(root, app)
        assert app.model.area == 1
        assert app.chunk_size.get() == "250000"
        app.chunk_size.set("17")
        app.density.set("230")
        assert "230" in app.estimate.get()
        output = folder / "cloud.txt"
        with patch("app.filedialog.asksaveasfilename", return_value=str(output)), patch("app.generate", wraps=generate) as generated:
            app.generate_button.invoke()
            wait(root, app)
            assert generated.call_args.kwargs["chunk_size"] == 17
        assert app.last_output == output
        assert np.loadtxt(output).shape == (230, 7)
        np.testing.assert_array_equal(np.loadtxt(output)[:, 3:6], np.tile([255, 0, 0], (230, 1)))
        app.chunk_size.set("0")
        assert str(app.generate_button["state"]) == "disabled"
        app.chunk_size.set("12.5")
        assert str(app.generate_button["state"]) == "disabled"
        app.chunk_size.set("250000")
        app.rgb_check.invoke()
        assert not app.use_labels.get()
        assert str(app.labels_check["state"]) == "disabled"
        plain = folder / "xyz.txt"
        app.start_generation(plain)
        wait(root, app)
        assert np.loadtxt(plain).shape == (230, 3)
        app.density.set("0")
        assert str(app.generate_button["state"]) == "disabled"
        app.density.set("100")
        assert str(app.generate_button["state"]) == "normal"
        with patch("app.messagebox.showerror") as error:
            app.start_generation(output)
            wait(root, app)
            assert error.called
        assert np.loadtxt(output).shape == (230, 7)
        assert str(app.generate_button["state"]) == "normal"
        assert "open3d" not in sys.modules
        print("PASS: RGB/labels, configured batch size, invalid settings, RGB-off XYZ output, error recovery; no 3D dependency")
    finally:
        root.destroy()
