"""Directory scanning and the in-memory size tree. No GUI code here.

The tree is OmniDiskSweeper's model: every folder knows its total size and
keeps its children sorted from biggest to smallest, all the way down.
Sizes are *disk usage* (allocated blocks), i.e. what deleting frees.
"""

import gc
import os
import queue
import stat
import sys
import threading
from array import array

from . import kinds

# Node.flags
UNREADABLE = 1   # folder could not be listed (permissions, vanished, ...)
OTHER_FS = 2     # mount point of another filesystem, not descended into
SYMLINK = 4

_NO_KINDS = array("q", [0] * kinds.COUNT)


def _kind_totals():
    return array("q", _NO_KINDS)


def _default_threads():
    # With the GIL, more than two threads mostly fight over it (measured);
    # free-threaded Python builds can really use the cores.
    if getattr(sys, "_is_gil_enabled", lambda: True)():
        return 2
    return min(16, os.cpu_count() or 2)


class Node:
    """A file or folder.

    `children` is None for files and a list (biggest first) for folders.
    `kinds` is the kind index (int) for a file, and for a folder a list with
    the bytes taken by each kind in its whole subtree.
    `count` is the number of files in the subtree (1 for a file).
    The root node's `name` is its absolute path.
    """

    __slots__ = ("name", "size", "count", "parent", "children", "kinds", "flags")

    def __init__(self, name, size, parent=None, children=None, kinds_=kinds.OTHER, flags=0):
        self.name = name
        self.size = size
        self.count = 0 if children is not None else 1
        self.parent = parent
        self.children = children
        self.kinds = kinds_
        self.flags = flags

    @property
    def is_dir(self):
        return self.children is not None

    def path(self):
        parts = []
        node = self
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return os.path.join(*reversed(parts))

    def chain(self):
        """Nodes from the root down to self (both included)."""
        nodes = []
        node = self
        while node is not None:
            nodes.append(node)
            node = node.parent
        nodes.reverse()
        return nodes

    def kind(self):
        """Kind index for coloring: a folder takes its dominant kind."""
        if self.children is None:
            return self.kinds
        best = max(range(kinds.COUNT), key=self.kinds.__getitem__)
        return best if self.kinds[best] > 0 else kinds.OTHER

    def kind_vector(self):
        if self.children is not None:
            return self.kinds
        vector = [0] * kinds.COUNT
        vector[self.kinds] = self.size
        return vector

    def __repr__(self):
        return f"<Node {self.name!r} {self.size}>"


class Scanner:
    """Scans a folder with a small pool of threads.

    Progress counters (`files`, `bytes`, `current`) can be read from another
    thread while `run()` works; `cancel()` stops it early.
    """

    def __init__(self, path, one_filesystem=True, threads=None):
        self.path = os.path.realpath(path)
        self.one_filesystem = one_filesystem
        self.threads = threads or _default_threads()
        self.files = 0
        self.bytes = 0
        self.errors = 0
        self.current = self.path
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._seen_inodes = set()

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def run(self):
        """Scan and return the root Node, or None if cancelled."""
        st = os.stat(self.path)
        if not stat.S_ISDIR(st.st_mode):
            raise NotADirectoryError(self.path)
        root = Node(self.path, st.st_blocks * 512, children=[], kinds_=_kind_totals())
        self._device = st.st_dev
        self._pending = 1
        self._done = threading.Event()
        self._queue = queue.SimpleQueue()
        self._queue.put((root, self.path))
        # Millions of new objects would trigger endless useless GC passes.
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            workers = [threading.Thread(target=self._work, daemon=True)
                       for _ in range(self.threads)]
            for worker in workers:
                worker.start()
            self._done.wait()
            for _worker in workers:
                self._queue.put(None)
            for worker in workers:
                worker.join()
            if self.cancelled:
                return None
            finalize(root)
            # Keep the tree out of the collector's sight for good: one full
            # pass over a million nodes is a half-second freeze of the UI.
            # Trees are freed by reference counting instead (see release()).
            gc.freeze()
        finally:
            if gc_was_enabled:
                gc.enable()
        return root

    def _work(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            subdirs = () if self.cancelled else self._scan_dir(*item)
            with self._lock:
                self._pending += len(subdirs) - 1
                if self._pending == 0:
                    self._done.set()
            for sub in subdirs:
                self._queue.put(sub)

    def _scan_dir(self, node, path):
        self.current = path
        children = node.children
        totals = node.kinds
        subdirs = []
        files = size_sum = 0
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        st = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    mode = st.st_mode
                    size = st.st_blocks * 512
                    if stat.S_ISDIR(mode):
                        child = Node(entry.name, size, node, [], _kind_totals())
                        if self.one_filesystem and st.st_dev != self._device:
                            child.flags = OTHER_FS
                        else:
                            subdirs.append((child, entry.path))
                    else:
                        if st.st_nlink > 1:  # count hard-linked data once
                            key = (st.st_dev, st.st_ino)
                            with self._lock:
                                if key in self._seen_inodes:
                                    size = 0
                                else:
                                    self._seen_inodes.add(key)
                        if stat.S_ISLNK(mode):
                            child = Node(entry.name, size, node, flags=SYMLINK)
                        else:
                            kind = kinds.kind_of(entry.name, bool(mode & 0o111), size)
                            child = Node(entry.name, size, node, kinds_=kind)
                            totals[kind] += size
                        files += 1
                    size_sum += size
                    children.append(child)
        except OSError:
            node.flags |= UNREADABLE
            with self._lock:
                self.errors += 1
        with self._lock:
            self.files += files
            self.bytes += size_sum
        return subdirs


def finalize(root):
    """Roll sizes, counts and kind totals up the tree and sort every folder."""
    order = []
    stack = [root]
    while stack:
        node = stack.pop()
        order.append(node)
        stack.extend(child for child in node.children if child.children is not None)
    for node in reversed(order):  # children before parents
        size = node.size
        count = 0
        totals = node.kinds
        for child in node.children:
            size += child.size
            count += child.count
            if child.children is not None:
                for i, value in enumerate(child.kinds):
                    totals[i] += value
        node.size = size
        node.count = count
        node.children.sort(key=_size_key, reverse=True)


def _size_key(node):
    return node.size


def _propagate(start, d_size, d_count, d_kinds):
    """Add deltas to `start` and all its ancestors, keeping order sorted."""
    node = start
    while node is not None:
        node.size += d_size
        node.count += d_count
        for i, value in enumerate(d_kinds):
            node.kinds[i] += value
        if node.parent is not None:
            node.parent.children.sort(key=_size_key, reverse=True)
        node = node.parent


def release(node):
    """Drop the parent links of a subtree that is no longer needed.

    Scanned trees are frozen out of the garbage collector (Scanner.run), and
    child -> parent links make cycles: breaking them lets plain reference
    counting free the nodes."""
    stack = [node]
    while stack:
        current = stack.pop()
        current.parent = None
        if current.children:
            stack.extend(current.children)


def detach(node):
    """Remove a node from the tree after it was deleted from disk."""
    parent = node.parent
    parent.children.remove(node)
    _propagate(parent, -node.size, -node.count, [-v for v in node.kind_vector()])
    release(node)


def replace(old, new):
    """Swap `old` for a freshly scanned `new` (e.g. after a rescan)."""
    parent = old.parent
    new.name = old.name if parent is not None else new.name
    new.parent = parent
    if parent is None:
        return new
    index = parent.children.index(old)
    parent.children[index] = new
    parent.children.sort(key=_size_key, reverse=True)
    old_kinds, new_kinds = old.kind_vector(), new.kind_vector()
    _propagate(parent, new.size - old.size, new.count - old.count,
               [b - a for a, b in zip(old_kinds, new_kinds)])
    release(old)
    return new
