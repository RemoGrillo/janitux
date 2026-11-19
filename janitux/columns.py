"""OmniDiskSweeper-style column browser.

Each column lists one folder's children, biggest first. Selecting a folder
opens its contents in a new column to the right, so the path from the scan
root to the current item is always visible left to right.
"""

from gi.repository import Gdk, GLib, Graphene, Gtk, Pango

from .charts import rect, rgba
from .common import color_of, icon_for, percent, size_text
from .i18n import _, plural
from .scanner import OTHER_FS, UNREADABLE
from .suspects import is_cache


class ShareBar(Gtk.Widget):
    """Thin bar: how much of the parent folder this item takes."""

    def __init__(self):
        super().__init__(hexpand=True)
        self.set_size_request(-1, 4)
        self.fraction = 0.0
        self.color = (0.5, 0.5, 0.5)

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        ink = self.get_color()
        snapshot.append_color(rgba((ink.red, ink.green, ink.blue), 0.08), rect(0, 0, width, height))
        filled = max(2.0, width * self.fraction) if self.fraction > 0 else 0
        snapshot.append_color(rgba(self.color), rect(0, 0, filled, height))


class Row(Gtk.Box):
    def __init__(self):
        super().__init__(spacing=10, margin_top=5, margin_bottom=5, margin_start=4)
        self.icon = Gtk.Image()
        self.name = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE, hexpand=True)
        self.badge = Gtk.Label(label=_("cache"), css_classes=["badge"], valign=Gtk.Align.CENTER)
        self.bar = ShareBar()
        self.size = Gtk.Label(xalign=1, css_classes=["numeric", "caption", "dim-label"])
        self.arrow = Gtk.Image(icon_name="go-next-symbolic", css_classes=["dim-label"])
        title = Gtk.Box(spacing=6)
        title.append(self.name)
        title.append(self.badge)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True,
                        valign=Gtk.Align.CENTER)
        texts.append(title)
        texts.append(self.bar)
        self.append(self.icon)
        self.append(texts)
        self.append(self.size)
        self.append(self.arrow)

    def show(self, node, folder):
        self.icon.set_from_icon_name(icon_for(node))
        self.name.set_label(node.name)
        self.badge.set_visible(is_cache(node))
        self.size.set_label(size_text(node.size))
        self.bar.fraction = node.size / folder.size if folder.size else 0
        self.bar.color = color_of(node)
        self.bar.queue_draw()
        self.arrow.set_opacity(1 if node.is_dir and node.children else 0)
        tip = f"{node.name}\n{size_text(node.size)} · {percent(node.size, folder.size)}"
        if node.is_dir:
            tip += " · " + plural(node.count, "{n} file", "{n} files")
        if node.flags & OTHER_FS:
            tip += "\n" + _("not scanned: other filesystem")
        elif node.flags & UNREADABLE:
            tip += "\n" + _("not readable")
        self.set_tooltip_text(tip)


class Column(Gtk.ScrolledWindow):
    WIDTH = 290

    def __init__(self, browser, folder):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_width=False)
        self.set_size_request(self.WIDTH, -1)
        self.browser = browser
        self.folder = folder
        # The model holds names; rows read the node at the same position.
        self.nodes = list(folder.children)
        model = Gtk.StringList.new([n.name for n in self.nodes])
        self.selection = Gtk.SingleSelection(model=model, autoselect=False, can_unselect=True)
        self.selection.set_selected(Gtk.INVALID_LIST_POSITION)
        self.selection.connect("notify::selected", self._on_selected)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup)
        factory.connect("bind", self._bind)
        self.view = Gtk.ListView(model=self.selection, factory=factory)
        self.view.add_css_class("navigation-sidebar")
        self.view.connect("activate", lambda _v, pos: browser.on_activate(self.nodes[pos]))
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.view.add_controller(keys)
        if self.nodes:
            self.set_child(self.view)
        else:
            text = _("not readable") if folder.flags & UNREADABLE else "∅"
            self.set_child(Gtk.Label(label=text, css_classes=["dim-label"]))

    @property
    def selected(self):
        pos = self.selection.get_selected()
        return None if pos == Gtk.INVALID_LIST_POSITION else self.nodes[pos]

    def select(self, node):
        pos = self.nodes.index(node)
        self.selection.set_selected(pos)
        return pos

    def focus_selected(self):
        pos = self.selection.get_selected()
        if pos == Gtk.INVALID_LIST_POSITION and self.nodes:
            pos = 0
            self.selection.set_selected(0)
        if self.nodes:
            self.view.scroll_to(pos, Gtk.ListScrollFlags.FOCUS, None)

    def _setup(self, _factory, item):
        row = Row()
        menu = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        menu.connect("pressed", self._on_right_click, item)
        row.add_controller(menu)
        item.set_child(row)

    def _bind(self, _factory, item):
        item.get_child().show(self.nodes[item.get_position()], self.folder)

    def _on_selected(self, *_args):
        self.browser.column_selected(self, self.selected)

    def _on_right_click(self, gesture, _n, x, y, item):
        self.selection.set_selected(item.get_position())
        self.browser.on_context_menu(gesture.get_widget(), x, y)

    def _on_key(self, _ctrl, keyval, _code, _state):
        if keyval == Gdk.KEY_Right:
            return self.browser.move_focus(self, +1)
        if keyval == Gdk.KEY_Left:
            return self.browser.move_focus(self, -1)
        return False


class ColumnBrowser(Gtk.ScrolledWindow):
    def __init__(self, on_select, on_activate, on_context_menu):
        super().__init__(vscrollbar_policy=Gtk.PolicyType.NEVER, hexpand=True)
        self.on_select = on_select
        self.on_activate = on_activate
        self.on_context_menu = on_context_menu
        self.columns = []
        self.box = Gtk.Box()
        # The deepest column is where the attention is: whenever the strip's
        # width changes, keep its right end in view (we scroll by hand).
        self.set_child(Gtk.Viewport(child=self.box, scroll_to_focus=False))
        self.get_hadjustment().connect("changed", self._show_last_column)
        self._quiet = False

    def set_root(self, root):
        self._truncate(-1)
        self._append(root)

    def reveal(self, node, focus=True):
        """Select `node` (any depth), opening all columns on the way."""
        chain = node.chain()
        self._quiet = True
        try:
            self._truncate(0)
            self.columns[0].selection.set_selected(Gtk.INVALID_LIST_POSITION)
            column = self.columns[0]
            for depth, child in enumerate(chain[1:]):
                column = self.columns[depth]
                column.select(child)
        finally:
            self._quiet = False
        if focus and len(chain) > 1:
            column.focus_selected()
        self.on_select(node)

    def move_focus(self, column, step):
        index = self.columns.index(column) + step
        if 0 <= index < len(self.columns):
            self.columns[index].focus_selected()
            self._show_column(self.columns[index])
            return True
        return False

    def column_selected(self, column, node):
        index = self.columns.index(column)
        self._truncate(index)
        if node is not None and node.is_dir and not node.flags & OTHER_FS:
            self._append(node)
        if not self._quiet:
            self.on_select(node if node is not None else column.folder)

    def _append(self, folder):
        if self.columns:
            self.box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        column = Column(self, folder)
        self.box.append(column)
        self.columns.append(column)
        self._stretch_last()

    def _truncate(self, index):
        """Remove every column after position `index` (-1: all)."""
        while len(self.columns) > index + 1:
            column = self.columns.pop()
            separator = column.get_prev_sibling()
            self.box.remove(column)
            if separator is not None:
                self.box.remove(separator)
        self._stretch_last()

    def _stretch_last(self):
        """The deepest column takes whatever room is left: no empty gap."""
        for i, column in enumerate(self.columns):
            column.set_hexpand(i == len(self.columns) - 1)

    def _show_last_column(self, adjustment):
        # The viewport is still configuring the adjustment: scroll right after.
        def scroll():
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())
        GLib.idle_add(scroll)

    def _show_column(self, column):
        adjustment = self.get_hadjustment()
        ok, origin = column.compute_point(self.box, Graphene.Point())
        if not ok:
            return
        left, right = origin.x, origin.x + column.get_width()
        value, page = adjustment.get_value(), adjustment.get_page_size()
        if left < value:
            adjustment.set_value(left)
        elif right > value + page:
            adjustment.set_value(right - page)
