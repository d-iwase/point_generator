"""Small Tk operation window; no Open3D, graphics context or 3D preview."""
from pathlib import Path
import queue
import threading
import time
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from generator import Cancelled, load_obj, point_count, generate

APP_DIR = Path(__file__).resolve().parent


class Application:
    def __init__(self, root):
        self.root = root
        root.title("point_generator | IFC変換・点群生成")
        root.geometry("840x780")
        root.minsize(800, 760)
        root.option_add("*Font", ("Yu Gothic UI", 10))
        self.model = None
        self.busy = False
        self.closing = False
        self.cancel_event = threading.Event()
        self.events = queue.Queue()
        self.last_output = None
        self.ifc_source = None
        self.converted_obj = None
        self.mm_scale = tk.BooleanVar(value=True)
        self.keep_direction = tk.BooleanVar(value=False)
        self.ifc_path_text = tk.StringVar(value="IFCファイルを選択してください")
        self.ifc_result_text = tk.StringVar(value="")
        self.started = 0
        self.point_progress = None
        self.timing = tk.StringVar(value="待機中")
        self.path_text = tk.StringVar(value="OBJファイルを選択してください")
        self.info = tk.StringVar(value="モデルはまだ読み込まれていません。")
        self.density = tk.StringVar(value="1000")
        self.chunk_size = tk.StringVar(value="250000")
        self.use_rgb = tk.BooleanVar(value=True)
        self.use_labels = tk.BooleanVar(value=True)
        self.format_text = tk.StringVar()
        self.estimate = tk.StringVar(value="生成予定: -")
        self.status = tk.StringVar(value="OBJを読み込み、密度を指定して点群を生成します。")
        self.output_text = tk.StringVar(value="")
        footer = ttk.Frame(root, padding=(24, 8, 24, 16))
        footer.pack(side="bottom", fill="x")
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.build_ifc_tab()
        body = ttk.Frame(self.notebook, padding=24)
        self.point_tab = body
        self.notebook.add(body, text="OBJから点群を生成")
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text="OBJから表面点群を生成", font=("Yu Gothic UI", 18, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 18))
        self.open_button = ttk.Button(body, text="OBJを選択", command=self.choose_obj)
        self.open_button.grid(row=1, column=0, sticky="w")
        ttk.Label(body, textvariable=self.path_text, wraplength=680).grid(row=2, column=0, sticky="w", pady=(8, 6))
        ttk.Label(body, textvariable=self.info).grid(row=3, column=0, sticky="w", pady=(0, 16))
        controls = ttk.Frame(body)
        controls.grid(row=4, column=0, sticky="ew")
        ttk.Label(controls, text="密度（点 / m²）").pack(side="left", padx=(0, 12))
        self.density_entry = ttk.Entry(controls, textvariable=self.density, width=18)
        self.density_entry.pack(side="left")
        ttk.Label(body, text="OBJの1単位を1mとして計算します。", foreground="#555555").grid(row=5, column=0, sticky="w", pady=(6, 10))
        options = ttk.Frame(body)
        options.grid(row=6, column=0, sticky="w", pady=(0, 12))
        ttk.Label(options, text="1回の処理点数").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.chunk_entry = ttk.Entry(options, textvariable=self.chunk_size, width=18)
        self.chunk_entry.grid(row=0, column=1, sticky="w")
        ttk.Label(options, text="この点数ごとに同じTXTへ書き込みます。総点数は変わりません。").grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 8))
        self.rgb_check = ttk.Checkbutton(options, text="MTLのRGBを保存", variable=self.use_rgb, command=self.rgb_changed)
        self.rgb_check.grid(row=2, column=0, sticky="w")
        self.labels_check = ttk.Checkbutton(options, text="RGBごとのラベルを保存", variable=self.use_labels, command=self.refresh)
        self.labels_check.grid(row=2, column=1, columnspan=2, sticky="w")
        ttk.Label(options, textvariable=self.format_text).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(body, textvariable=self.estimate, font=("Yu Gothic UI", 12, "bold")).grid(row=7, column=0, sticky="w", pady=(0, 14))
        actions = ttk.Frame(body)
        actions.grid(row=8, column=0, sticky="w")
        self.generate_button = ttk.Button(actions, text="点群を生成してTXT保存", command=self.choose_output)
        self.generate_button.pack(side="left", padx=(0, 12))
        self.cancel_button = ttk.Button(actions, text="中止", command=self.cancel)
        self.cancel_button.pack(side="left")
        self.progress = ttk.Progressbar(footer, maximum=100)
        self.progress.pack(fill="x", pady=(0, 8))
        ttk.Label(footer, textvariable=self.timing, wraplength=720).pack(anchor="w", pady=(0, 4))
        ttk.Label(footer, textvariable=self.status, wraplength=720).pack(anchor="w")
        ttk.Label(footer, textvariable=self.output_text, wraplength=720, foreground="#17625b").pack(anchor="w", pady=(8, 0))
        self.density.trace_add("write", lambda *_: self.refresh())
        self.chunk_size.trace_add("write", lambda *_: self.refresh())
        self.build_pipeline_tab()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        root.after(100, self.poll)

    @staticmethod
    def enable(widget, value):
        widget.configure(state="normal" if value else "disabled")

    def build_pipeline_tab(self):
        panel = ttk.Frame(self.notebook, padding=24)
        self.notebook.insert(0, panel, text="IFCから点群まで一括生成")
        self.notebook.select(panel)
        ttk.Label(panel, text="IFC → OBJ・MTL → 点群TXT", font=("Yu Gothic UI", 18, "bold")).pack(anchor="w", pady=(0, 18))
        ttk.Label(panel, text="設定後、IFCとOBJの保存先を選ぶと、点群の保存まで自動で進みます。\nOBJと同名のMTL、末尾が _surface.txt の点群を同じフォルダに保存します。", wraplength=700).pack(anchor="w", pady=(0, 18))
        self.pipeline_controls = []
        for label, variable in (("密度（点 / m²）", self.density), ("1回の処理点数", self.chunk_size)):
            row = ttk.Frame(panel)
            row.pack(anchor="w", pady=6)
            ttk.Label(row, text=label, width=22).pack(side="left")
            entry = ttk.Entry(row, textvariable=variable, width=18)
            entry.pack(side="left")
            self.pipeline_controls.append(entry)
        for label, variable, command in (
            ("MTLのRGBを保存", self.use_rgb, self.rgb_changed),
            ("RGBごとのラベルを保存", self.use_labels, self.refresh),
            ("追加倍率 0.001 を適用", self.mm_scale, self.refresh),
            ("元の向きを保持する", self.keep_direction, self.refresh)):
            control = ttk.Checkbutton(panel, text=label, variable=variable, command=command)
            control.pack(anchor="w", pady=5)
            self.pipeline_controls.append(control)
        ttk.Label(panel, text="設定は他のタブと共通です。追加倍率はIFCの単位の自動判定ではありません。", wraplength=700).pack(anchor="w", pady=10)
        self.pipeline_button = ttk.Button(panel, text="IFCを選んで一括生成", command=self.choose_pipeline)
        self.pipeline_button.pack(anchor="w", pady=10)
        self.pipeline_cancel = ttk.Button(panel, text="中止", command=self.cancel)
        self.pipeline_cancel.pack(anchor="w")
        ttk.Label(panel, text="途中で中止・失敗した場合も、保存済みのOBJ・MTLは残ります。", wraplength=700).pack(anchor="w", pady=12)

    def choose_pipeline(self):
        if self.busy:
            return
        try:
            density, chunk = float(self.density.get()), int(self.chunk_size.get())
            if not math.isfinite(density) or density <= 0 or chunk < 1:
                raise ValueError('密度は0より大きい有限の数値、処理点数は1以上の整数にしてください。')
        except ValueError as exc:
            messagebox.showerror('設定を確認してください', str(exc), parent=self.root)
            return
        source = filedialog.askopenfilename(parent=self.root, title="一括生成するIFCを選択", filetypes=[("IFCモデル", "*.ifc")])
        if not source:
            return
        output = filedialog.asksaveasfilename(parent=self.root, title="OBJ・MTL・点群の保存名", defaultextension=".obj",
            filetypes=[("OBJモデル", "*.obj")], initialdir=str(Path(source).parent), initialfile=Path(source).stem + '.obj', confirmoverwrite=False)
        if not output:
            return
        from pipeline import run_pipeline
        options = dict(density=density, chunk_size=chunk, use_rgb=self.use_rgb.get(),
            use_labels=self.use_labels.get(), use_mm_scale=self.mm_scale.get(), keep_direction=self.keep_direction.get())
        self.ifc_source = Path(source)
        self.ifc_path_text.set(source)
        self.converted_obj = None
        self.ifc_result_text.set('')
        self.output_text.set('')
        self.status.set('一括生成を開始しています...')
        self.progress.configure(mode='indeterminate')
        self.progress.start(15)
        self.begin('saved', lambda: run_pipeline(source, output, **options, cancel=self.cancel_event,
            event=lambda kind, data: self.events.put((kind, data))))

    def build_ifc_tab(self):
        panel = ttk.Frame(self.notebook, padding=24)
        self.notebook.add(panel, text="IFCをOBJに変換")
        ttk.Label(panel, text="IFCをOBJ / MTLに変換", font=("Yu Gothic UI", 18, "bold")).pack(anchor="w", pady=(0, 18))
        self.ifc_open_button = ttk.Button(panel, text="IFCを選択", command=self.choose_ifc)
        self.ifc_open_button.pack(anchor="w")
        ttk.Label(panel, textvariable=self.ifc_path_text, wraplength=700).pack(anchor="w", pady=(8, 20))
        settings = ttk.LabelFrame(panel, text="変換設定（ifc-objと同じ動作）", padding=14)
        settings.pack(fill="x", pady=(0, 20))
        self.mm_check = ttk.Checkbutton(settings, text="追加倍率 0.001 を適用（元アプリの標準設定）", variable=self.mm_scale)
        self.mm_check.pack(anchor="w", pady=(0, 8))
        self.direction_check = ttk.Checkbutton(settings, text="元の向きを保持する", variable=self.keep_direction)
        self.direction_check.pack(anchor="w", pady=(0, 10))
        ttk.Label(settings, text="倍率オフ時は1倍。向きの保持がオフなら主方向をX軸へ合わせます。\n原点はモデルの中心に移動します。", wraplength=680).pack(anchor="w")
        ttk.Label(settings, text="この倍率はIFCの単位の自動判定ではなく、形状取得後の追加倍率です。", wraplength=680).pack(anchor="w", pady=(8, 0))
        actions = ttk.Frame(panel)
        actions.pack(anchor="w")
        self.ifc_convert_button = ttk.Button(actions, text="OBJ / MTLに変換して保存", command=self.choose_ifc_output)
        self.ifc_convert_button.pack(side="left", padx=(0, 12))
        self.ifc_cancel_button = ttk.Button(actions, text="中止", command=self.cancel)
        self.ifc_cancel_button.pack(side="left")
        ttk.Label(panel, textvariable=self.ifc_result_text, wraplength=700).pack(anchor="w", pady=(18, 14))
        self.use_converted_button = ttk.Button(panel, text="変換したOBJを点群生成に読み込む", command=self.use_converted_obj)
        self.use_converted_button.pack(anchor="w")
        ttk.Label(panel, text="読込後に密度・生成予定点数を確認し、点群生成を実行してください。", wraplength=700).pack(anchor="w", pady=(8, 0))

    def choose_ifc(self):
        if self.busy:
            return
        filename = filedialog.askopenfilename(parent=self.root, title="IFCを選択", filetypes=[("IFCモデル", "*.ifc")])
        if filename:
            self.ifc_source = Path(filename)
            self.ifc_path_text.set(filename)
            self.converted_obj = None
            self.ifc_result_text.set("")
            self.status.set("変換設定を確認し、保存先を選択してください。")
            self.refresh()

    def choose_ifc_output(self):
        if self.busy or self.ifc_source is None:
            return
        filename = filedialog.asksaveasfilename(parent=self.root, title="OBJの保存先", defaultextension=".obj",
            filetypes=[("OBJモデル", "*.obj")], initialdir=str(self.ifc_source.parent),
            initialfile=self.ifc_source.stem + ".obj", confirmoverwrite=False)
        if filename:
            self.start_ifc_conversion(filename)

    def start_ifc_conversion(self, filename):
        if self.busy or self.ifc_source is None:
            return
        source = self.ifc_source
        mm, keep_direction = self.mm_scale.get(), self.keep_direction.get()
        self.status.set("IFCを変換しています...")
        self.output_text.set("")
        self.progress.configure(mode="indeterminate")
        self.progress.start(15)
        def work():
            from ifc_conversion import convert_ifc
            return convert_ifc(source, filename, use_mm_scale=mm, keep_direction=keep_direction,
                               cancel=self.cancel_event, progress=lambda text: self.events.put(("detail", text)))
        self.begin("converted", work)

    def use_converted_obj(self):
        if self.busy or self.converted_obj is None:
            return
        self.notebook.select(self.point_tab)
        self.start_load(self.converted_obj)

    def refresh(self):
        valid = False
        if self.model is not None:
            try:
                count = point_count(self.model, self.density.get())
                self.estimate.set(f"生成予定: {count:,} 点")
                valid = True
            except (ValueError, OverflowError):
                self.estimate.set("密度に0より大きい数値を入力してください。")
        else:
            self.estimate.set("生成予定: -")
        try:
            if int(self.chunk_size.get()) < 1:
                raise ValueError()
        except ValueError:
            valid = False
            self.estimate.set("1回の処理点数には1以上の整数を入力してください。")
        columns = "X Y Z"
        if self.use_rgb.get():
            columns += " R G B"
            if self.use_labels.get():
                columns += " LABEL"
        self.format_text.set(f"保存する列: {columns}")
        self.enable(self.open_button, not self.busy)
        self.enable(self.density_entry, not self.busy)
        self.enable(self.chunk_entry, not self.busy)
        self.enable(self.rgb_check, not self.busy)
        self.enable(self.labels_check, not self.busy and self.use_rgb.get())
        self.enable(self.generate_button, valid and not self.busy)
        self.enable(self.cancel_button, self.busy and not self.cancel_event.is_set())
        self.enable(self.ifc_open_button, not self.busy)
        self.enable(self.mm_check, not self.busy)
        self.enable(self.direction_check, not self.busy)
        self.enable(self.ifc_convert_button, not self.busy and self.ifc_source is not None)
        self.enable(self.ifc_cancel_button, self.busy and not self.cancel_event.is_set())
        self.enable(self.use_converted_button, not self.busy and self.converted_obj is not None)
        for control in self.pipeline_controls:
            self.enable(control, not self.busy)
        self.enable(self.pipeline_controls[3], not self.busy and self.use_rgb.get())
        self.enable(self.pipeline_button, not self.busy)
        self.enable(self.pipeline_cancel, self.busy and not self.cancel_event.is_set())

    def rgb_changed(self):
        if not self.use_rgb.get():
            self.use_labels.set(False)
        self.refresh()

    def choose_obj(self):
        if self.busy:
            return
        filename = filedialog.askopenfilename(parent=self.root, title="OBJを選択", filetypes=[("OBJモデル", "*.obj")])
        if filename:
            self.start_load(filename)

    def begin(self, kind, work):
        if self.busy:
            return
        self.busy = True
        self.cancel_event.clear()
        self.started = time.monotonic()
        self.generation_started = self.started
        self.pipeline_timing = None
        self.mapping_output = None
        self.point_progress = None
        self.timing.set("経過 0秒")
        self.progress.configure(value=0)
        self.refresh()
        def run():
            try:
                self.events.put((kind, work()))
            except Cancelled as exc:
                self.events.put(("cancelled", str(exc)))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def start_load(self, filename):
        if self.busy:
            return
        self.status.set("OBJを読み込み、表面積を計算しています...")
        self.progress.configure(mode="indeterminate")
        self.progress.start(15)
        self.begin("loaded", lambda: load_obj(filename, self.cancel_event,
            progress=lambda stage, done, total: self.events.put(("load_progress", (stage, done, total)))))

    def choose_output(self):
        if self.busy or self.model is None:
            return
        filename = filedialog.asksaveasfilename(parent=self.root, title="点群TXTの保存先", defaultextension=".txt",
            filetypes=[("点群テキスト", "*.txt")], initialdir=str(APP_DIR),
            initialfile=self.model.path.stem + "_surface.txt", confirmoverwrite=False)
        if filename:
            self.start_generation(filename)

    def start_generation(self, filename):
        if self.busy or self.model is None:
            return
        try:
            density = float(self.density.get())
            total = point_count(self.model, density)
            chunk_size = int(self.chunk_size.get())
            if chunk_size < 1:
                raise ValueError("1回の処理点数には1以上の整数を指定してください。")
        except (ValueError, OverflowError) as exc:
            messagebox.showerror("設定を確認してください", str(exc), parent=self.root)
            return
        self.status.set(f"0 / {total:,} 点を生成・保存中...")
        self.output_text.set("")
        self.progress.configure(mode="determinate")
        model = self.model
        use_rgb, use_labels = self.use_rgb.get(), self.use_labels.get()
        self.begin("saved", lambda: generate(model, density, filename, cancel=self.cancel_event,
                    chunk_size=chunk_size, use_rgb=use_rgb, use_labels=use_labels,
                    progress=lambda done, count: self.events.put(("progress", (done, count)))))

    def cancel(self):
        if self.busy:
            self.cancel_event.set()
            self.status.set("中止しています。現在の処理区間が終わるまでお待ちください。")
            self.refresh()

    def poll(self):
        for _ in range(100):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'pipeline_timing':
                self.pipeline_timing = data
                continue
            if kind == 'mapping_saved':
                self.mapping_output = data
                continue
            if kind == 'generation_started':
                self.generation_started = time.monotonic()
                self.progress.stop()
                self.progress.configure(mode='determinate', value=0)
                if not self.cancel_event.is_set():
                    self.status.set('点群生成を開始しています...')
                continue
            if kind == "progress":
                done, total = data
                self.point_progress = (done, total)
                self.progress.configure(value=min(99.9, 100 * done / total))
                if not self.cancel_event.is_set():
                    self.status.set(f"点群生成・書込　{100 * done / total:.1f}%　（{done:,} / {total:,} 点）" if done < total else "書込終了・保存を確定中...")
                continue
            if kind == "load_progress":
                stage, done, total = data
                self.progress.stop()
                if done is None:
                    self.progress.configure(mode="indeterminate")
                    self.progress.start(15)
                else:
                    self.progress.configure(mode="determinate", value=100 * done / max(1, total))
                    stage += f"　{100 * done / max(1, total):.1f}%（{done / 1048576:.1f} / {total / 1048576:.1f} MB）"
                if not self.cancel_event.is_set():
                    self.status.set(stage)
                continue
            if kind == "detail":
                if not self.cancel_event.is_set():
                    self.status.set(data)
                continue
            intermediate = kind in ('pipeline_converted', 'pipeline_loaded')
            if intermediate:
                kind = 'converted' if kind == 'pipeline_converted' else 'loaded'
            else:
                self.busy = False
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self.timing.set(f"経過 {time.monotonic() - self.started:.1f}秒")
            if kind == "converted":
                obj, mtl, counts = data
                self.converted_obj = obj
                self.ifc_result_text.set(f"OBJ: {obj}\nMTL: {mtl}\n要素: {counts[0]:,} / 頂点: {counts[1]:,} / 面: {counts[2]:,}")
                self.progress.configure(value=100)
                self.status.set(f"IFC変換完了（{time.monotonic() - self.started:.1f}秒）。点群生成は開始していません。")
                self.output_text.set(f"保存先: {obj.parent}")
            elif kind == "loaded":
                self.progress.configure(value=100)
                self.model = data
                self.path_text.set(str(data.path))
                extent = " / ".join(f"{value:,.4g}" for value in data.extent)
                colors = f"色別ラベル: {int(data.triangle_labels.max()) + 1:,} 種類"
                if data.missing_colors:
                    colors += f"（材質色なし {data.missing_colors:,} 面は灰色）"
                self.info.set(f"三角形: {len(data.triangles):,} 面　表面積: {data.area:,.6g} m²\n大きさ X / Y / Z: {extent} m\n{colors}")
                self.status.set("読込完了。生成予定の点数を確認してから実行してください。")
                self.output_text.set("")
            elif kind == "saved":
                self.last_output, count = data
                self.progress.configure(value=100)
                self.status.set(f"完了: {count:,} 点を保存しました（{time.monotonic() - self.started:.1f}秒）。")
                self.output_text.set(f"保存先: {self.last_output}")
                if self.mapping_output is not None:
                    self.output_text.set(f"点群: {self.last_output}\n対応表: {self.mapping_output}")
                if self.pipeline_timing is not None:
                    durations = self.pipeline_timing
                    self.timing.set(
                        f"合計 {durations['total']:.1f}秒\n"
                        f"IFC → OBJ・MTL変換: {durations['conversion']:.1f}秒\n"
                        f"OBJ読込・点群準備: {durations['preparation']:.1f}秒\n"
                        f"点群生成・TXT保存: {durations['generation']:.1f}秒")
                    self.status.set(f"一括生成完了: {count:,} 点を保存しました。")
            else:
                self.status.set(data)
                if kind == "error" and not self.closing:
                    messagebox.showerror("処理できませんでした", data, parent=self.root)
            if intermediate:
                self.status.set('OBJ・MTL保存済み。点群生成の準備を続けています...')
            self.refresh()
        if self.busy:
            elapsed = time.monotonic() - self.started
            timing = f"経過 {elapsed:.0f}秒"
            if self.point_progress and not self.cancel_event.is_set():
                done, total = self.point_progress
                generation_elapsed = time.monotonic() - self.generation_started
                if done and generation_elapsed >= 1 and done < total:
                    timing += f"　｜　{done / generation_elapsed:,.0f} 点/秒　｜　残り約 {generation_elapsed * (total - done) / done:.0f}秒"
            self.timing.set(timing)
        if self.closing and not self.busy:
            self.root.destroy()
            return
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            self.closing = True
            self.cancel()
        else:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Application(root)
    root.mainloop()
