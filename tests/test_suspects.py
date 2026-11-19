import unittest

from janitux import kinds
from janitux.scanner import Node, _kind_totals, finalize
from janitux.suspects import explained, find_suspects, path_depth

MB = 1 << 20


def tree(spec, root="/home/alex"):
    """Build a size tree from {"name": size or {...}} (sizes in MB)."""
    def fill(node, items):
        for name, value in items.items():
            if isinstance(value, dict):
                child = Node(name, 0, node, [], _kind_totals())
                fill(child, value)
            else:
                child = Node(name, int(value * MB), node, kinds_=kinds.OTHER)
                node.kinds[kinds.OTHER] += child.size
            node.children.append(child)
    top = Node(root, 0, children=[], kinds_=_kind_totals())
    fill(top, spec)
    finalize(top)
    return top


def names(suspects):
    return [s.node.name for s in suspects]


class SuspectsTest(unittest.TestCase):
    def test_buried_single_file_beats_a_big_diffuse_folder(self):
        root = tree({
            "Photos": {f"img{i}.jpg": 1 for i in range(1000)},        # 1000 MB, 1000 files
            "a": {"b": {"c": {"d": {"huge.iso": 600}}}},               # 600 MB, 1 file, deep
        })
        self.assertEqual(names(find_suspects(root))[0], "huge.iso")

    def test_explaining_away_lists_the_file_not_its_folders(self):
        root = tree({
            "a": {"b": {"c": {"big.img": 900, "note.txt": 0.1}}},
            "other": {f"f{i}": 1 for i in range(100)},
        })
        found = names(find_suspects(root))
        self.assertEqual(found[0], "big.img")
        for folder in ("a", "b", "c"):
            self.assertNotIn(folder, found)  # nothing big is left in them

    def test_suspects_never_overlap_and_add_up(self):
        root = tree({
            "Videos": {"x.mkv": 400, "y.mkv": 300, "clips": {f"c{i}.mp4": 5 for i in range(40)}},
            "Games": {"Starfall": {"data": {"world.pak": 700, "audio.pak": 150}}},
            ".cache": {f"blob{i}": 2 for i in range(200)},
        })
        suspects = find_suspects(root)
        nodes = [s.node for s in suspects]
        for node in nodes:
            parent = node.parent
            while parent is not None:  # no suspect contains a suspect picked before it…
                if parent in nodes:
                    self.assertGreater(nodes.index(parent), nodes.index(node))
                parent = parent.parent
        self.assertLessEqual(explained(suspects), root.size)  # …and the remainders add up

    def test_rebuildable_cache_is_more_suspicious_than_a_twin_folder(self):
        twin = {f"f{i}": 3 for i in range(50)}
        root = tree({"keep": dict(twin), ".cache": dict(twin), "pad": {f"p{i}": 1 for i in range(500)}})
        found = names(find_suspects(root))
        self.assertLess(found.index(".cache"), found.index("keep"))

    def test_small_things_and_the_root_are_never_accused(self):
        root = tree({"tiny": {"a.txt": 1, "b.txt": 2}, "c.txt": 3})
        self.assertEqual(find_suspects(root), [])

    def test_depth_counts_from_the_disk_root(self):
        self.assertEqual(path_depth("/"), 0)
        self.assertEqual(path_depth("/home/alex"), 2)
        root = tree({"Projects": {"big.bin": 50}})
        self.assertEqual(find_suspects(root)[0].depth, 4)  # /home/alex/Projects/big.bin


if __name__ == "__main__":
    unittest.main()
