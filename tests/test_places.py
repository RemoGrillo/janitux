import os
import tempfile
import unittest

from janitux.places import empty_trash, measure_trash


def write(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(os.urandom(size))


class TrashTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.trash = os.path.join(self.tmp.name, "Trash")
        write(f"{self.trash}/files/movie.mkv", 200_000)
        write(f"{self.trash}/files/project/a/b.bin", 50_000)
        for name in ("movie.mkv", "project"):
            write(f"{self.trash}/info/{name}.trashinfo", 100)
        write(f"{self.trash}/directorysizes", 10)
        write(f"{self.tmp.name}/keep.txt", 10)  # outside the trash: must survive

    def tearDown(self):
        self.tmp.cleanup()

    def test_measure(self):
        size, items = measure_trash([self.trash])
        self.assertEqual(items, 2)
        self.assertGreaterEqual(size, 250_000)

    def test_empty_removes_items_and_their_info_only(self):
        self.assertEqual(empty_trash([self.trash]), 0)
        self.assertEqual(os.listdir(f"{self.trash}/files"), [])
        self.assertEqual(os.listdir(f"{self.trash}/info"), [])
        self.assertFalse(os.path.exists(f"{self.trash}/directorysizes"))
        self.assertTrue(os.path.exists(f"{self.tmp.name}/keep.txt"))
        self.assertEqual(measure_trash([self.trash])[1], 0)

    def test_missing_trash_is_harmless(self):
        missing = os.path.join(self.tmp.name, "nope")
        self.assertEqual(measure_trash([missing]), (0, 0))
        self.assertEqual(empty_trash([missing]), 0)


if __name__ == "__main__":
    unittest.main()
