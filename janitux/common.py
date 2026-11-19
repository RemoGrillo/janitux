"""Small helpers shared by the widgets."""

import locale
import os

from gi.repository import Adw, GLib

from . import kinds
from .scanner import OTHER_FS, SYMLINK, UNREADABLE

# Folder names that only hold regenerable data: safe cleaning candidates.
CACHE_NAMES = frozenset((
    ".cache", "cache", "Cache", "caches", "Caches", "CachedData", "GPUCache",
    "Code Cache", "ShaderCache", "thumbnails", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".npm", ".gradle", ".ccache",
))


def palette():
    dark = Adw.StyleManager.get_default().get_dark()
    return kinds.PALETTE_DARK if dark else kinds.PALETTE_LIGHT


def color_of(node):
    return palette()[node.kind()]


def size_text(size):
    return GLib.format_size(max(0, size))


def percent(part, whole):
    value = 100 * part / whole if whole > 0 else 0
    if 0 < value < 0.1:
        return "<0.1%"
    return locale.format_string("%.1f%%" if value < 10 else "%.0f%%", value)


def display_name(node):
    """A node's name; for the scan root (whose name is a path) its last part."""
    if node.parent is None:
        return os.path.basename(node.name.rstrip("/")) or node.name
    return node.name


def is_cache(node):
    return node.is_dir and node.name in CACHE_NAMES


def icon_for(node):
    if node.flags & OTHER_FS:
        return "drive-harddisk-symbolic"
    if node.flags & UNREADABLE:
        return "action-unavailable-symbolic"
    if node.flags & SYMLINK:
        return "insert-link-symbolic"
    if node.is_dir:
        return "folder-symbolic"
    return kinds.ICONS[node.kinds]
