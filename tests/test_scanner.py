import os
import tempfile
import unittest

from janitux import kinds
from janitux.scanner import Scanner, detach, replace


def write(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(os.urandom(size))  # random: no sparse/compressed surprises


def du(path):
    return os.lstat(path).st_blocks * 512


class ScannerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(f"{self.root}/big/movie.mkv", 300_000)
        write(f"{self.root}/big/nested/deeper/photo.JPG", 120_000)
        write(f"{self.root}/small/notes.txt", 5_000)
        write(f"{self.root}/small/libfoo.so.1.2", 9_000)
        write(f"{self.root}/top.bin", 50_000)
        os.symlink("big/movie.mkv", f"{self.root}/link")
        write(f"{self.root}/links/a.iso", 200_000)
        os.link(f"{self.root}/links/a.iso", f"{self.root}/links/b.iso")
        self.tree = Scanner(self.root).run()

    def tearDown(self):
        self.tmp.cleanup()

    def find(self, relpath):
        node = self.tree
        for part in relpath.split("/"):
            node = next(c for c in node.children if c.name == part)
        return node

    def test_sizes_match_du_and_hardlinks_count_once(self):
        total = 0
        for dirpath, dirnames, filenames in os.walk(self.root):
            total += du(dirpath)
            total += sum(du(os.path.join(dirpath, f)) for f in filenames)
        total -= du(f"{self.root}/links/b.iso")  # same inode as a.iso
        self.assertEqual(self.tree.size, total)
        self.assertEqual(self.tree.count, 8)
        # whichever name is met first carries the data, the other is free
        sizes = sorted(c.size for c in self.find("links").children)
        self.assertEqual(sizes, [0, du(f"{self.root}/links/a.iso")])

    def test_children_sorted_biggest_first_at_every_level(self):
        stack = [self.tree]
        while stack:
            node = stack.pop()
            sizes = [c.size for c in node.children]
            self.assertEqual(sizes, sorted(sizes, reverse=True))
            stack.extend(c for c in node.children if c.is_dir)
        self.assertEqual(self.tree.children[0].name, "big")
        self.assertEqual(self.tree.children[0].children[0].name, "movie.mkv")

    def test_paths_and_kinds(self):
        photo = self.find("big/nested/deeper/photo.JPG")
        self.assertEqual(photo.path(), f"{self.root}/big/nested/deeper/photo.JPG")
        self.assertEqual(photo.kinds, kinds.IMAGE)
        self.assertEqual(self.find("small/libfoo.so.1.2").kinds, kinds.PROGRAM)
        self.assertEqual(self.find("big").kind(), kinds.VIDEO)
        self.assertEqual(sum(self.tree.kinds), sum(
            n.size for n in self._files(self.tree) if not n.flags))

    def test_detach_updates_ancestors(self):
        before = self.tree.size
        photo = self.find("big/nested/deeper/photo.JPG")
        detach(photo)
        self.assertEqual(self.tree.size, before - photo.size)
        self.assertEqual(self.find("big/nested").count, 0)
        self.assertEqual(self.tree.kinds[kinds.IMAGE], 0)

    def test_replace_after_rescan(self):
        write(f"{self.root}/small/new.iso", 600_000)
        small = self.find("small")
        fresh = Scanner(small.path()).run()
        replace(small, fresh)
        self.assertEqual(self.tree.children[0].name, "small")  # now the biggest
        self.assertEqual(fresh.path(), f"{self.root}/small")
        self.assertGreater(self.tree.kinds[kinds.ARCHIVE], 0)

    def test_cancel(self):
        scanner = Scanner(self.root)
        scanner.cancel()
        self.assertIsNone(scanner.run())

    @staticmethod
    def _files(node):
        stack = [node]
        while stack:
            n = stack.pop()
            if n.is_dir:
                stack.extend(n.children)
            else:
                yield n


if __name__ == "__main__":
    unittest.main()
