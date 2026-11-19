"""The lineup: the main suspects of a scan, with the clues against each one."""

import os
import time

from gi.repository import Gtk, Pango

from . import kinds
from .columns import ShareBar
from .common import color_of, icon_for, percent, size_text
from .i18n import _
from .suspects import explained, find_suspects

MONTH = 30.44 * 86400


def clues(suspect):
    """Short reasons why this item is a suspect."""
    node = suspect.node
    found = []
    if suspect.trashed:
        found.append(_("already in the trash"))
    elif suspect.rebuildable:
        found.append(_("rebuildable cache"))
    if node.children is None:
        found.append(_("single file"))
    else:
        found.append(_("{n} files").format(n=f"{node.count:n}"))
        vector = node.kind_vector()
        kind = node.kind()
        if kind != kinds.OTHER and vector[kind] >= 0.7 * max(1, sum(vector)):
            found.append(_("mostly {kind}").format(kind=kinds.NAMES[kind].lower()))
    if suspect.depth >= 5:
        found.append(_("{n} levels deep").format(n=suspect.depth))
    path = node.path()
    try:
        months = int((time.time() - os.lstat(path).st_mtime) / MONTH)
    except OSError:
        months = 0
    if months >= 24:
        found.append(_("untouched for {n} years").format(n=months // 12))
    elif months >= 6:
        found.append(_("untouched for {n} months").format(n=months))
    if not os.access(os.path.dirname(path), os.W_OK):
        found.append(_("needs admin rights"))
    return found


class Lineup(Gtk.Box):
    def __init__(self, on_navigate):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.on_navigate = on_navigate
        self.summary = Gtk.Label(xalign=0, wrap=True, css_classes=["dim-label"], margin_start=6,
                                 margin_bottom=4)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.add_css_class("navigation-sidebar")
        self.list.connect("row-selected", self._on_row_selected)
        self.append(Gtk.Label(label=_("Main suspects"), xalign=0, css_classes=["title-3"],
                              margin_start=6))
        self.append(self.summary)
        self.append(Gtk.ScrolledWindow(child=self.list, vexpand=True,
                                       hscrollbar_policy=Gtk.PolicyType.NEVER))
        self._nodes = []
        self._quiet = False

    def investigate(self, root):
        """Rank the suspects of the (possibly changed) tree under `root`."""
        suspects = find_suspects(root)
        self.list.remove_all()
        self._nodes = [s.node for s in suspects]
        if not suspects:
            self.summary.set_label(_("No suspects: nothing here is big enough to worry about."))
            return
        self.summary.set_label(_("{n} suspects hold {size}, {pct} of the scanned space").format(
            n=len(suspects), size=size_text(explained(suspects)),
            pct=percent(explained(suspects), root.size)))
        top = suspects[0].score
        for rank, suspect in enumerate(suspects, 1):
            self.list.append(self._row(rank, suspect, top))

    def mark(self, node):
        """Highlight `node` if it is in the lineup (the selection changed elsewhere)."""
        self._quiet = True
        try:
            if node in self._nodes:
                self.list.select_row(self.list.get_row_at_index(self._nodes.index(node)))
            else:
                self.list.unselect_all()
        finally:
            self._quiet = False

    def _on_row_selected(self, _list, row):
        if row is not None and not self._quiet:
            self.on_navigate(self._nodes[row.get_index()])

    @staticmethod
    def _row(rank, suspect, top):
        node = suspect.node
        name = Gtk.Label(label=node.name, xalign=0, hexpand=True, css_classes=["heading"],
                         ellipsize=Pango.EllipsizeMode.MIDDLE)
        size = Gtk.Label(label=size_text(node.size), css_classes=["heading", "numeric"])
        heading = Gtk.Box(spacing=8)
        heading.append(name)
        heading.append(size)
        evidence = Gtk.Label(label=" · ".join(clues(suspect)), xalign=0, wrap=True,
                             css_classes=["caption"])
        where = Gtk.Label(label=os.path.dirname(node.path()), xalign=0,
                          css_classes=["caption", "dim-label"], ellipsize=Pango.EllipsizeMode.START)
        meter = ShareBar()
        meter.fraction = suspect.score / top if top > 0 else 0
        meter.color = color_of(node)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        for widget in (heading, evidence, where, meter):
            texts.append(widget)
        box = Gtk.Box(spacing=12, margin_top=8, margin_bottom=8, margin_start=4, margin_end=4)
        box.append(Gtk.Label(label=str(rank), width_chars=2, valign=Gtk.Align.START,
                             css_classes=["title-3", "numeric", "dim-label"]))
        box.append(Gtk.Image(icon_name=icon_for(node), pixel_size=24, valign=Gtk.Align.START,
                             margin_top=2))
        box.append(texts)
        row = Gtk.ListBoxRow(child=box)
        row.set_tooltip_text(node.path())
        return row
