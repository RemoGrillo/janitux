"""Right-hand panel: the charts plus details and actions for the selection."""

import os

from gi.repository import Adw, Gio, GLib, Gtk, Pango

from . import kinds
from .charts import Sunburst, Treemap, rect, rgba, rounded_rect
from .common import display_name, icon_for, palette, percent, size_text
from .i18n import _


class KindBar(Gtk.Widget):
    """Stacked bar: how the bytes split across file kinds."""

    HEIGHT = 12

    def __init__(self):
        super().__init__(hexpand=True, has_tooltip=True)
        self.set_size_request(-1, self.HEIGHT)
        self.values = [0] * kinds.COUNT
        self.connect("query-tooltip", self._on_tooltip)
        Adw.StyleManager.get_default().connect("notify::dark", lambda *_a: self.queue_draw())

    def set_values(self, values):
        self.values = list(values)
        self.queue_draw()

    def _spans(self):
        total = sum(self.values)
        width = self.get_width()
        x = 0.0
        for kind, value in enumerate(self.values):
            if value > 0 and total > 0:
                w = width * value / total
                yield kind, x, w
                x += w

    def do_snapshot(self, snapshot):
        colors = palette()
        for kind, x, w in self._spans():
            w = max(w - 2, 1.5)  # 2px gap between segments
            snapshot.push_rounded_clip(rounded_rect(x, 0, w, self.HEIGHT, 3))
            snapshot.append_color(rgba(colors[kind]), rect(x, 0, w, self.HEIGHT))
            snapshot.pop()

    def _on_tooltip(self, _widget, x, _y, _keyboard, tooltip):
        total = sum(self.values)
        for kind, start, w in self._spans():
            if start <= x < start + w:
                tooltip.set_text(f"{kinds.NAMES[kind]}: {size_text(self.values[kind])} "
                                 f"({percent(self.values[kind], total)})")
                return True
        return False


class Dot(Gtk.Widget):
    def __init__(self, kind):
        super().__init__(valign=Gtk.Align.CENTER)
        self.kind = kind
        self.set_size_request(10, 10)

    def do_snapshot(self, snapshot):
        snapshot.push_rounded_clip(rounded_rect(0, 0, 10, 10, 5))
        snapshot.append_color(rgba(palette()[self.kind]), rect(0, 0, 10, 10))
        snapshot.pop()


class Inspector(Gtk.Box):
    def __init__(self, on_navigate):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                         margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.set_size_request(360, -1)

        self.sunburst = Sunburst(on_navigate, self._on_hover)
        self.treemap = Treemap(on_navigate, self._on_hover)
        self.charts = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.charts.add_titled(self.sunburst, "sunburst", _("Sunburst"))
        self.charts.add_titled(self.treemap, "treemap", _("Treemap"))
        self.charts.connect("notify::visible-child", lambda *_a: self._update_chart())
        switcher = Gtk.StackSwitcher(stack=self.charts, halign=Gtk.Align.CENTER)
        self.caption = Gtk.Label(css_classes=["caption", "dim-label"],
                                 ellipsize=Pango.EllipsizeMode.MIDDLE)
        self.append(switcher)
        self.append(self.charts)
        self.append(self.caption)
        self.append(Gtk.Separator())

        # Details of the selected item.
        self.icon = Gtk.Image(pixel_size=32, valign=Gtk.Align.START)
        self.name = Gtk.Label(xalign=0, css_classes=["title-3"], hexpand=True,
                              ellipsize=Pango.EllipsizeMode.MIDDLE)
        self.size = Gtk.Label(xalign=1, css_classes=["title-2", "numeric"])
        self.path = Gtk.Label(xalign=0, css_classes=["caption", "dim-label"], selectable=True,
                              ellipsize=Pango.EllipsizeMode.START)
        self.meta = Gtk.Label(xalign=0, css_classes=["caption"], wrap=True)
        heading = Gtk.Box(spacing=10)
        heading.append(self.name)
        heading.append(self.size)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        texts.append(heading)
        texts.append(self.path)
        texts.append(self.meta)
        details = Gtk.Box(spacing=12)
        details.append(self.icon)
        details.append(texts)
        self.append(details)

        self.kind_bar = KindBar()
        self.legend = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4,
                                  column_spacing=12, row_spacing=2, homogeneous=False)
        self.append(self.kind_bar)
        self.append(self.legend)

        actions = Gtk.Box(spacing=6)
        actions.append(Gtk.Button(label=_("Open"), action_name="win.open"))
        actions.append(Gtk.Button(label=_("Show in folder"), action_name="win.show-in-folder"))
        actions.append(Gtk.Box(hexpand=True))
        trash = Gtk.Button(action_name="win.trash", css_classes=["destructive-action"],
                           tooltip_text=_("Move to trash") + " (Del)")
        trash.set_child(Adw.ButtonContent(icon_name="user-trash-symbolic", label=_("Move to trash")))
        actions.append(trash)
        more = Gio.Menu()
        more.append(_("Copy path"), "win.copy-path")
        more.append(_("Rescan folder"), "win.rescan-folder")
        more.append(_("Delete permanently…"), "win.delete")
        actions.append(Gtk.MenuButton(icon_name="view-more-symbolic", menu_model=more,
                                      direction=Gtk.ArrowType.UP))
        self.append(actions)

        self.root = self.focus = self.selected = None
        # Legend dots take the palette of the current light/dark style.
        Adw.StyleManager.get_default().connect(
            "notify::dark", lambda *_a: self.selected and self._update_details())

    def show(self, root, selected):
        self.root = root
        self.selected = selected
        self.focus = selected if selected.is_dir else selected.parent
        self._update_chart()
        self._update_details()

    def refresh(self):
        self.sunburst.refresh()
        self.treemap.refresh()

    def _update_chart(self):
        if self.focus is not None:
            self.charts.get_visible_child().show(self.focus, self.selected)
        self._on_hover(None)

    def _on_hover(self, node):
        if node is None:
            text = ""
        else:
            text = f"{node.name} — {size_text(node.size)} · {percent(node.size, self.focus.size)}"
        self.caption.set_label(text or " ")

    def _update_details(self):
        node = self.selected
        self.icon.set_from_icon_name(icon_for(node))
        self.name.set_label(display_name(node))
        self.size.set_label(size_text(node.size))
        self.path.set_label(node.path())
        self.path.set_tooltip_text(node.path())
        parts = []
        if node.is_dir:
            parts.append(_("{n} files").format(n=f"{node.count:n}"))
        if node.parent is not None:
            parts.append(_("{pct} of folder").format(pct=percent(node.size, node.parent.size)))
            parts.append(_("{pct} of total").format(pct=percent(node.size, self.root.size)))
        try:
            mtime = os.lstat(node.path()).st_mtime
            date = GLib.DateTime.new_from_unix_local(int(mtime)).format("%x")
            parts.append(_("modified {date}").format(date=date))
        except OSError:
            pass
        self.meta.set_label(" · ".join(parts))

        values = node.kind_vector()
        self.kind_bar.set_values(values)
        self.legend.remove_all()
        for kind, value in enumerate(values):
            if value > 0:
                item = Gtk.Box(spacing=6)
                item.append(Dot(kind))
                item.append(Gtk.Label(label=kinds.NAMES[kind], css_classes=["caption"]))
                item.append(Gtk.Label(label=size_text(value),
                                      css_classes=["caption", "dim-label", "numeric"]))
                self.legend.append(item)
