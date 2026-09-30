"""Run the existing converters sequentially, retaining completed outputs."""
from pathlib import Path
import math
import time
from generator import load_obj, generate, check_cancel
from ifc_conversion import convert_ifc


def run_pipeline(source, output, *, density, chunk_size=250000, use_rgb=True,
                 use_labels=True, use_mm_scale=True, keep_direction=False,
                 cancel=None, event=None):
    output = Path(output)
    if not output.suffix:
        output = output.with_suffix('.obj')
    density = float(density)
    if not math.isfinite(density) or density <= 0:
        raise ValueError('密度には0より大きい有限の数値を入力してください。')
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError('1回の処理点数には1以上の整数を指定してください。')
    if use_labels and not use_rgb:
        raise ValueError('ラベル保存にはRGB保存を有効にしてください。')
    cloud = output.with_name(output.stem + '_surface.txt')
    mapping = output.with_name(output.stem + '_labels.csv')
    targets = [output, output.with_suffix('.mtl'), cloud]
    if use_labels:
        targets.append(mapping)
    for path in targets:
        if path.exists():
            raise FileExistsError(f'同名ファイルが存在します。別の保存名を選んでください。\n{path}')
    def emit(kind, data):
        if event:
            event(kind, data)
    started = time.monotonic()
    members = {}
    converted = convert_ifc(source, output, use_mm_scale=use_mm_scale,
        keep_direction=keep_direction, cancel=cancel,
        progress=lambda text: emit('detail', 'IFC変換　' + text),
        object_callback=lambda name, data: members.__setitem__(name, data))
    converted_at = time.monotonic()
    emit('pipeline_converted', converted)
    check_cancel(cancel)
    model = load_obj(converted[0], cancel, progress=lambda *data: emit('load_progress', data))
    check_cancel(cancel)
    if use_labels:
        from label_mapping import save_mapping
        emit('detail', 'IFC部材と点群ラベルの対応表を保存中...')
        saved_mapping = save_mapping(model, members, mapping, cancel)
        emit('mapping_saved', saved_mapping)
    loaded_at = time.monotonic()
    emit('pipeline_loaded', model)
    emit('generation_started', None)
    result = generate(model, density, cloud, chunk_size=chunk_size,
        use_rgb=use_rgb, use_labels=use_labels, cancel=cancel,
        progress=lambda done, total: emit('progress', (done, total)))
    finished = time.monotonic()
    emit('pipeline_timing', {
        'conversion': converted_at - started,
        'preparation': loaded_at - converted_at,
        'generation': finished - loaded_at,
        'total': finished - started,
    })
    return result
