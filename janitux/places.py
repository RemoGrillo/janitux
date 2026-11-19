"""Mounted disks and trash folders. No GUI code here.

The trash follows the freedesktop.org Trash specification: the home trash
in $XDG_DATA_HOME/Trash, plus one per disk in <mount>/.Trash-<uid> or
<mount>/.Trash/<uid>, each with files/ (the items) and info/ (where they
came from).
"""

import os
import re
import shutil

from .scanner import Scanner, release

SKIP_MOUNTS = ("/boot", "/efi", "/snap/", "/var/lib/snapd")


def mounts():
    """(device, mount point, filesystem type) of the real disks, once each."""
    found, seen = [], set()
    try:
        with open("/proc/self/mounts", encoding="utf-8") as table:
            lines = table.readlines()
    except OSError:
        return found
    for line in lines:
        device, mount, fstype = line.split()[:3]
        mount = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), mount)
        if (not device.startswith("/dev/") or device.startswith("/dev/loop")
                or fstype == "squashfs" or mount.startswith(SKIP_MOUNTS) or device in seen):
            continue
        seen.add(device)
        found.append((device, mount, fstype))
    return found


def home_trash():
    if os.path.exists("/.flatpak-info"):  # the sandbox remaps XDG_DATA_HOME
        data = os.path.expanduser("~/.local/share")
    else:
        data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(data, "Trash")


def trash_dirs():
    """Every trash folder of this user that exists."""
    uid = os.getuid()
    candidates = [home_trash()]
    for _device, mount, _fstype in mounts():
        candidates += [os.path.join(mount, f".Trash-{uid}"), os.path.join(mount, ".Trash", str(uid))]
    found = []
    for path in candidates:
        real = os.path.realpath(path)
        if os.path.isdir(os.path.join(real, "files")) and real not in found:
            found.append(real)
    return found


def measure_trash(dirs):
    """(bytes on disk, number of items) in the given trash folders."""
    size = items = 0
    for trash in dirs:
        files = os.path.join(trash, "files")
        try:
            items += len(os.listdir(files))
            tree = Scanner(files).run()
        except OSError:
            continue
        size += tree.size
        release(tree)
    return size, items


def empty_trash(dirs):
    """Delete everything in the given trash folders; return how many items resisted."""
    failed = 0
    for trash in dirs:
        files = os.path.join(trash, "files")
        info = os.path.join(trash, "info")
        try:
            names = os.listdir(files)
        except OSError:
            continue
        for name in names:
            path = os.path.join(files, name)
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if os.path.lexists(path):
                failed += 1
                continue
            try:
                os.remove(os.path.join(info, name + ".trashinfo"))
            except OSError:
                pass
        for leftover in ("directorysizes",):  # caches that describe the old content
            try:
                os.remove(os.path.join(trash, leftover))
            except OSError:
                pass
        shutil.rmtree(os.path.join(trash, "expunged"), ignore_errors=True)
    return failed
