"""Write one summary row per RGB label."""
import csv
from pathlib import Path
import tempfile
from generator import check_cancel


def save_mapping(model, members, output, cancel=None):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f'対応表が既に存在します: {output}')
    groups = {}
    for index, (name, label) in enumerate(zip(model.triangle_objects, model.triangle_labels)):
        if index % 4096 == 0:
            check_cancel(cancel)
        label = int(label)
        if label not in groups:
            groups[label] = {'rgb': tuple(int(v) for v in model.triangle_rgb[index]), 'members': set()}
        groups[label]['members'].add(name)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', newline='',
                dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            fields = ['label', 'R', 'G', 'B', 'member_names', 'ifc_class', 'object_type', 'member_count']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for label, group in sorted(groups.items()):
                check_cancel(cancel)
                rgb = group['rgb']
                types, object_types, names = set(), set(), set()
                for name in sorted(group['members']):
                    check_cancel(cancel)
                    member = members[name]
                    if member.get('name'):
                        names.add(member['name'])
                    if member.get('ifc_class'):
                        types.add(member['ifc_class'])
                    if member.get('object_type'):
                        object_types.add(member['object_type'])
                writer.writerow(dict(label=label, R=rgb[0], G=rgb[1], B=rgb[2],
                    member_names='; '.join(sorted(names)),
                    ifc_class='; '.join(sorted(types)), object_type='; '.join(sorted(object_types)),
                    member_count=len(group['members'])))
        check_cancel(cancel)
        temporary.rename(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output.resolve()
