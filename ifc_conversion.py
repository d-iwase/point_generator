"""ifc-obj GUI-compatible conversion, with cancellation and safe paired output."""
from pathlib import Path
import tempfile

from generator import check_cancel
from obj_export import export_obj


def convert_ifc(source, output, *, use_mm_scale=True, keep_direction=False, cancel=None, progress=None, object_callback=None):
    source, output = Path(source), Path(output)
    if not source.is_file() or source.suffix.lower() != ".ifc":
        raise ValueError("IFCファイルを選択してください。")
    if not output.suffix:
        output = output.with_suffix(".obj")
    if output.suffix.lower() != ".obj":
        raise ValueError("保存先を.objにしてください。")
    if output.exists() or output.with_suffix(".mtl").exists():
        raise FileExistsError("同名のOBJまたはMTLが存在します。別の保存名を選んでください。")
    check_cancel(cancel)
    from ifc_geometry import convert_ifc_to_obj

    def report(text):
        check_cancel(cancel)
        if progress:
            translations = {
                'Loading IFC file...': '1/5 IFCファイルを読込中...',
                'Checking units...': '1/5 単位を確認中...',
                'Calculating model direction...': '2/5 モデルの向きを計算中...',
                'Keeping the original direction.': '2/5 元の向きを保持',
                'Checking size and position...': '3/5 大きさ・位置を確認中...',
                'Writing OBJ/MTL files...': '4/5 OBJ・MTLを作成中...',
                'Writing OBJ...': '4/5 OBJを作成中...',
                'Conversion completed.': '5/5 保存の準備中...',
                'OBJとMTLを保存しています...': '5/5 OBJ・MTLを保存中...',
            }
            for original, translated in translations.items():
                if text.startswith(original):
                    text = translated + text[len(original):].replace('elements', '要素処理済み')
                    break
            progress(text)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ifc-convert-", dir=output.parent) as folder:
        cached = Path(folder) / "model.obj"
        counts = convert_ifc_to_obj(source, cached, threads=1, scale=0.001 if use_mm_scale else 1.0,
            origin="center", align_xy=not keep_direction, progress_callback=report, object_callback=object_callback)
        report("OBJとMTLを保存しています...")
        obj, mtl = export_obj(cached, output, cancel=cancel)
    return obj.resolve(), mtl.resolve(), counts
