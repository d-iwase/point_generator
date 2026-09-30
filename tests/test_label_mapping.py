import csv
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
import numpy as np
from label_mapping import save_mapping


class MappingTests(unittest.TestCase):
    def test_shared_color_and_multiple_labels_per_member(self):
        model = SimpleNamespace(triangle_objects=['a', 'a', 'b', 'a'],
            triangle_labels=[0, 0, 0, 1],
            triangle_rgb=np.array([[255, 0, 0], [255, 0, 0], [255, 0, 0], [0, 0, 255]]))
        members = {'a': {'name': '柱, 一階', 'global_id': 'guid_a', 'ifc_class': 'IfcColumn', 'object_type': '柱'},
                   'b': {'name': '梁', 'global_id': 'guid_b', 'ifc_class': 'IfcBeam', 'object_type': '梁'}}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'labels.csv'
            save_mapping(model, members, output)
            with output.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row['label'] for row in rows], ['0', '1'])
            self.assertEqual(rows[0]['ifc_class'], 'IfcBeam; IfcColumn')
            self.assertEqual(rows[0]['object_type'], '柱; 梁')
            self.assertEqual(rows[0]['member_names'], '柱, 一階; 梁')
            self.assertEqual(rows[0]['member_count'], '2')
            self.assertEqual(rows[1]['member_count'], '1')
            self.assertNotIn('global_id', rows[0])
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                save_mapping(model, members, output)
            self.assertEqual(output.read_bytes(), before)
