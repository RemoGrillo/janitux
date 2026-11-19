"""Who is eating the disk? Rank the main suspects of a scan.

Every big item gets a suspicion score built like TF-IDF:

    suspicion(x) = share(x) · ln(1 + N / files(x)) · √depth(x) · bonus(x)

- share(x): the fraction of the scanned space x takes (the "term frequency").
- ln(1 + N / files(x)): how concentrated x is (the "inverse document
  frequency"). N is the number of files in the scan, files(x) the files inside
  x (1 for a file): a huge single file scores highest, a top folder holding
  half of everything barely counts.
- √depth(x): how many levels below "/" x lives. Big things buried deep are the
  ones nobody remembers.
- bonus(x): ×2 for data that can be rebuilt or is already thrown away (caches,
  the trash).

Suspects are then picked greedily, "explaining away": once x is picked, its
contents leave the race and its size and files are subtracted from its
parents, which are scored again with what is left. The result is a short list
of separate culprits whose sizes add up.
"""

import math
import os
from dataclasses import dataclass, field

CACHE_NAMES = frozenset((
    ".cache", "cache", "Cache", "caches", "Caches", "CachedData", "GPUCache",
    "Code Cache", "ShaderCache", "thumbnails", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".npm", ".gradle", ".ccache",
))

MIN_SIZE = 10 << 20      # never accuse anything smaller than 10 MB…
MAX_MIN_SIZE = 1 << 30   # …and anything from 1 GB up is always a candidate
MIN_SHARE = 0.005        # in between: at least 0.5% of the scan


def is_cache(node):
    return node.children is not None and node.name in CACHE_NAMES


def is_trash(node):
    name = node.name
    return name.startswith(".Trash") or (
        name == "Trash" and node.parent is not None and node.parent.name == "share")


def path_depth(path):
    """Levels below "/": "/" is 0, "/home/alex" is 2."""
    return len([part for part in path.split(os.sep) if part])


@dataclass(eq=False)
class Suspect:
    node: object
    depth: int
    rebuildable: bool = False
    trashed: bool = False
    size: int = 0           # what is left once better suspects are taken out
    files: int = 0
    score: float = 0.0
    ancestors: frozenset = field(default_factory=frozenset)


def score(size, files, depth, bonus, total, total_files):
    if size <= 0 or files <= 0 or total <= 0:
        return 0.0
    share = size / total
    concentration = math.log1p(total_files / files)
    return share * concentration * math.sqrt(depth) * bonus


def find_suspects(root, limit=10):
    """The main suspects of a scan, most suspicious first."""
    total, total_files = root.size, root.count
    if total <= 0 or total_files <= 0:
        return []
    threshold = max(MIN_SIZE, min(int(total * MIN_SHARE), MAX_MIN_SIZE))

    candidates = []
    stack = [(root, path_depth(root.path()), False, False, frozenset())]
    while stack:
        node, depth, rebuildable, trashed, ancestors = stack.pop()
        inner = ancestors | {id(node)}
        for child in node.children:
            if child.size < threshold:
                break  # children are sorted: the rest is smaller
            files = child.count if child.children is not None else 1
            if files <= 0:
                continue
            cache = rebuildable or is_cache(child)
            trash = trashed or is_trash(child)
            candidates.append(Suspect(child, depth + 1, cache, trash, child.size, files,
                                      ancestors=inner))
            if child.children:
                stack.append((child, depth + 1, cache, trash, inner))

    def rescore(suspect):
        bonus = 2.0 if suspect.rebuildable or suspect.trashed else 1.0
        suspect.score = score(suspect.size, suspect.files, suspect.depth, bonus,
                              total, total_files)

    for suspect in candidates:
        rescore(suspect)

    picked = []
    while candidates and len(picked) < limit:
        best = max(candidates, key=lambda s: s.score)
        if best.score <= 0:
            break
        picked.append(best)
        alive = []
        for suspect in candidates:
            if suspect is best or id(best.node) in suspect.ancestors:
                continue  # best itself, or something inside it
            if id(suspect.node) in best.ancestors:  # a folder holding best
                suspect.size -= best.size
                suspect.files -= best.files
                if suspect.size < threshold:
                    continue
                rescore(suspect)
            alive.append(suspect)
        candidates = alive
    return picked


def explained(suspects):
    """Bytes covered by the suspects together (their remainders never overlap)."""
    return sum(s.size for s in suspects)
