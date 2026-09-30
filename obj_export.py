"""Save the IFC geometry prepared by the ifc-obj conversion backend."""
from pathlib import Path
import tempfile
from generator import check_cancel


def export_obj(cached_obj, destination, cancel=None):
    source = Path(cached_obj)
    destination = Path(destination)
    if not destination.suffix:
        destination = destination.with_suffix(".obj")
    if destination.suffix.lower() != ".obj":
        raise ValueError("保存先には.objファイルを指定してください。")
    if destination.exists():
        raise FileExistsError("同名のOBJが存在します。別の名前を指定してください。")
    source_mtl = source.with_suffix(".mtl")
    if not source.is_file() or not source_mtl.is_file():
        raise FileNotFoundError("IFCの変換データがありません。IFCを読み込み直してください。")
    material_path = destination.with_suffix(".mtl")
    if material_path.exists():
        raise FileExistsError("同名のMTLが存在します。別の名前を指定してください。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_obj = temp_mtl = None
    material_committed = False
    try:
        check_cancel(cancel)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temp_obj = Path(stream.name)
            with source.open("rb") as incoming:
                replaced = False
                for index, line in enumerate(incoming):
                    if index % 4096 == 0:
                        check_cancel(cancel)
                    if line.startswith(b"mtllib "):
                        stream.write(f"mtllib {material_path.name}\n".encode("utf-8"))
                        replaced = True
                    else:
                        stream.write(line)
                if not replaced:
                    raise ValueError("変換データに材質ファイルの参照がありません。")
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
            temp_mtl = Path(stream.name)
            with source_mtl.open("rb") as incoming:
                while data := incoming.read(1024 * 1024):
                    check_cancel(cancel)
                    stream.write(data)
        check_cancel(cancel)
        # Windows rename does not overwrite an existing destination.
        temp_mtl.rename(material_path)
        material_committed = True
        temp_obj.rename(destination)
        return destination, material_path
    except Exception:
        if material_committed:
            material_path.unlink(missing_ok=True)
        raise
    finally:
        if temp_obj is not None:
            temp_obj.unlink(missing_ok=True)
        if temp_mtl is not None:
            temp_mtl.unlink(missing_ok=True)
