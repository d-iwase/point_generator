"""OBJ surface sampling without a renderer; based on surface_mode_v2's sampler."""
from dataclasses import dataclass
from pathlib import Path
import math
import tempfile

import numpy as np


class Cancelled(Exception):
    pass


def check_cancel(event):
    if event is not None and event.is_set():
        raise Cancelled("処理を中止しました。")


@dataclass
class Model:
    path: Path
    triangles: np.ndarray
    cumulative_areas: np.ndarray
    extent: np.ndarray
    triangle_rgb: np.ndarray
    triangle_labels: np.ndarray
    missing_colors: int = 0
    triangle_objects: object = None

    @property
    def area(self):
        return float(self.cumulative_areas[-1])


def load_obj(path, cancel=None, progress=None):
    path = Path(path)
    if path.suffix.lower() != ".obj":
        raise ValueError("OBJファイルを選択してください。")
    vertices, faces, face_materials, libraries = [], [], [], []
    current_material = None
    current_object = ''
    face_objects = []
    total_bytes = path.stat().st_size
    read_bytes = 0
    with path.open('rb') as stream:
        for line_number, raw in enumerate(stream):
            read_bytes += len(raw)
            raw = raw.decode('utf-8-sig', errors='replace')
            if line_number % 4096 == 0:
                check_cancel(cancel)
                if progress:
                    progress('OBJ読込', read_bytes, total_bytes)
            fields = raw.partition("#")[0].split()
            if not fields:
                continue
            try:
                if fields[0] == 'o':
                    current_object = raw.strip().split(maxsplit=1)[1] if len(fields) > 1 else ''
                elif fields[0] == "mtllib":
                    if len(fields) < 2:
                        raise ValueError("材質ファイル名がありません。")
                    reference = raw.partition("#")[0].strip().split(maxsplit=1)[1]
                    libraries.extend([reference] if (path.parent / reference).is_file() else reference.split())
                elif fields[0] == "usemtl":
                    current_material = raw.partition("#")[0].strip().split(maxsplit=1)[1] if len(fields) > 1 else None
                elif fields[0] == "v":
                    if len(fields) < 4:
                        raise ValueError("頂点にはXYZ座標が必要です。")
                    vertices.append([float(value) for value in fields[1:4]])
                elif fields[0] == "f":
                    indexes = []
                    for field in fields[1:]:
                        index = int(field.split("/")[0])
                        index = len(vertices) + index if index < 0 else index - 1
                        if not 0 <= index < len(vertices):
                            raise ValueError("面の頂点番号が範囲外です。")
                        indexes.append(index)
                    if len(indexes) < 3:
                        raise ValueError("面には3頂点以上が必要です。")
                    faces.extend((indexes[0], indexes[i], indexes[i + 1]) for i in range(1, len(indexes) - 1))
                    face_materials.extend([current_material] * (len(indexes) - 2))
                    face_objects.extend([current_object] * (len(indexes) - 2))
            except ValueError as exc:
                raise ValueError(f"OBJの{line_number + 1}行目: {exc}") from exc
    check_cancel(cancel)
    if not vertices or not faces:
        raise ValueError("面を持つOBJモデルが見つかりません。")
    if progress:
        progress('表面積を計算中', None, None)
    vertices = np.asarray(vertices, dtype=np.float64)
    if not np.isfinite(vertices).all():
        raise ValueError("座標にNaNまたは無限大が含まれています。")
    triangles = vertices[np.asarray(faces, dtype=np.int64)]
    areas = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1) / 2
    if not np.isfinite(areas).all():
        raise ValueError("面積を計算できません。座標の大きさを確認してください。")
    valid = areas > 0
    if not valid.any():
        raise ValueError("面積が0のモデルから点群は生成できません。")
    triangles, areas = triangles[valid], areas[valid]
    if progress:
        progress('RGB・ラベルを準備中', None, None)
    material_colors = load_materials(path.parent, libraries, cancel)
    face_materials = [name for name, keep in zip(face_materials, valid) if keep]
    colors = np.asarray([material_colors.get(name, (0.7, 0.7, 0.7)) for name in face_materials])
    rgb = (np.clip(colors, 0, 1) * 255).astype(np.uint8)
    _, labels = np.unique(rgb, axis=0, return_inverse=True)
    missing = sum(name not in material_colors for name in face_materials)
    cumulative = np.cumsum(areas)
    if not np.isfinite(cumulative[-1]):
        raise ValueError("モデルの表面積が大きすぎます。")
    check_cancel(cancel)
    used_vertices = triangles.reshape(-1, 3)
    objects = [name for name, keep in zip(face_objects, valid) if keep]
    return Model(path.resolve(), triangles, cumulative, np.ptp(used_vertices, axis=0), rgb, labels, missing, objects)


def load_materials(folder, libraries, cancel=None):
    colors = {}
    for library in dict.fromkeys(libraries):
        check_cancel(cancel)
        path = folder / library
        if not path.is_file():
            continue
        material = None
        with path.open(encoding="utf-8-sig", errors="replace") as stream:
            for line_number, line in enumerate(stream):
                if line_number % 4096 == 0:
                    check_cancel(cancel)
                line = line.partition("#")[0].strip()
                fields = line.split()
                if not fields:
                    continue
                if fields[0] == "newmtl":
                    material = line.split(maxsplit=1)[1] if len(fields) > 1 else None
                elif fields[0] == "Kd" and material is not None:
                    if len(fields) < 4:
                        raise ValueError(f"MTLの色指定が不正です: {path.name}:{line_number + 1}")
                    color = tuple(float(value) for value in fields[1:4])
                    if not all(math.isfinite(value) for value in color):
                        raise ValueError(f"MTLの色にNaNまたは無限大があります: {path.name}")
                    colors[material] = color
    return colors


def point_count(model, density):
    density = float(density)
    if not math.isfinite(density) or density <= 0:
        raise ValueError("密度には0より大きい有限の数値を入力してください。")
    value = model.area * density
    if not math.isfinite(value) or value > 2**53:
        raise ValueError("計算される点数が大きすぎます。密度を下げてください。")
    return max(1, int(round(value)))


def generate(model, density, output, *, cancel=None, progress=None, seed=None, chunk_size=250_000, use_rgb=False, use_labels=False):
    """Save all XYZ points in chunks; commit only the completed output file."""
    total = point_count(model, density)
    output = Path(output)
    if output.suffix.lower() != ".txt":
        raise ValueError("保存先の拡張子を.txtにしてください。")
    if output.exists():
        raise FileExistsError("同名のファイルが存在します。別の保存名を選んでください。")
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, (int, np.integer)) or chunk_size < 1:
        raise ValueError("1回の処理点数には1以上の整数を指定してください。")
    if use_labels and not use_rgb:
        raise ValueError("ラベル保存にはRGB保存を有効にしてください。")
    check_cancel(cancel)
    output.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=output.parent,
                                          prefix=".points-", suffix=".partial", delete=False) as stream:
            temporary = Path(stream.name)
            done = 0
            while done < total:
                check_cancel(cancel)
                count = min(chunk_size, total - done)
                selected = np.searchsorted(model.cumulative_areas, rng.random(count) * model.area, side="left")
                triangles = model.triangles[selected]
                r1, r2 = np.sqrt(rng.random(count)), rng.random(count)
                points = ((1 - r1)[:, None] * triangles[:, 0]
                          + (r1 * (1 - r2))[:, None] * triangles[:, 1]
                          + (r1 * r2)[:, None] * triangles[:, 2])
                columns, formats = [points], ["%.8f"] * 3
                if use_rgb:
                    columns.append(model.triangle_rgb[selected])
                    formats += ["%d"] * 3
                if use_labels:
                    columns.append(model.triangle_labels[selected, None])
                    formats.append("%d")
                # Update during a large batch without changing its sampling size.
                for offset in range(0, count, 10000):
                    check_cancel(cancel)
                    end = min(offset + 10000, count)
                    np.savetxt(stream, np.column_stack([column[offset:end] for column in columns]), fmt=formats)
                    if progress:
                        progress(done + end, total)
                done += count
        check_cancel(cancel)
        # Windows rename refuses to replace an existing file.
        temporary.rename(output)
        return output.resolve(), total
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
