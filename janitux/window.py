"""Main window: start page -> scanning -> results (columns + inspector)."""

import os
import shutil
import threading

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from .columns import ColumnBrowser
from .common import size_text
from .i18n import _
from .inspector import Inspector
from .pages import ScanPage, StartPage, header_with_menu
from .scanner import Scanner, detach, replace

CSS = """
.badge { font-size: 0.75em; font-weight: bold; padding: 0 6px; border-radius: 99px;
         background: alpha(currentColor, 0.12); }
levelbar.disk-usage block.roomy { background-color: @accent_bg_color; }
levelbar.disk-usage block.filling { background-color: @warning_bg_color; }
levelbar.disk-usage block.crowded { background-color: @error_bg_color; }
"""

SHORTCUTS = {
    "win.trash": ["Delete", "KP_Delete"],
    "win.delete": ["<Shift>Delete"],
    "win.open": ["<Ctrl>o"],
    "win.show-in-folder": ["<Ctrl><Shift>o"],
    "win.copy-path": ["<Ctrl><Shift>c"],
    "win.up": ["<Alt>Up", "BackSpace"],
    "win.rescan": ["F5", "<Ctrl>r"],
    "win.rescan-folder": ["<Shift>F5"],
    "win.new-scan": ["<Ctrl>n"],
}


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Janitux", default_width=1280,
                         default_height=820)
        self.root = None
        self.selected = None
        self.scanner = None
        self.freed = 0
        self.busy = False

        self.start_page = StartPage(self.scan, self._choose_folder)
        self.scan_page = ScanPage(self._cancel_scan)
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.pages.add_named(self.start_page, "start")
        self.pages.add_named(self.scan_page, "scan")
        self.pages.add_named(self._build_results(), "results")
        self.toasts = Adw.ToastOverlay(child=self.pages)
        self.set_content(self.toasts)

        for name, callback in (
            ("trash", self._trash), ("delete", self._confirm_delete),
            ("open", self._open), ("show-in-folder", self._show_in_folder),
            ("copy-path", self._copy_path), ("up", self._up),
            ("rescan", lambda: self.scan(self.root.path())),
            ("rescan-folder", self._rescan_folder), ("new-scan", self._new_scan),
        ):
            action = Gio.SimpleAction(name=name)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)
        self._update_actions()

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)

    # -- layout -------------------------------------------------------------
    def _build_results(self):
        header = header_with_menu()
        header.pack_start(Gtk.Button(icon_name="go-previous-symbolic", action_name="win.new-scan",
                                     tooltip_text=_("New scan") + " (Ctrl+N)"))
        header.pack_end(Gtk.Button(icon_name="view-refresh-symbolic", action_name="win.rescan",
                                   tooltip_text=_("Rescan") + " (F5)"))
        self.title = Adw.WindowTitle(title="Janitux")
        header.set_title_widget(self.title)

        self.columns = ColumnBrowser(self._on_select, self._on_activate, self._on_context_menu)
        self.inspector = Inspector(self._navigate)
        paned = Gtk.Paned(start_child=self.columns, end_child=self.inspector,
                          resize_start_child=True, resize_end_child=False,
                          shrink_start_child=False, shrink_end_child=False, position=700)
        view = Adw.ToolbarView(content=paned)
        view.add_top_bar(header)

        menu = Gio.Menu()
        for label, action in ((_("Open"), "win.open"), (_("Show in folder"), "win.show-in-folder"),
                              (_("Copy path"), "win.copy-path"),
                              (_("Rescan folder"), "win.rescan-folder")):
            menu.append(label, action)
        danger = Gio.Menu()
        danger.append(_("Move to trash"), "win.trash")
        danger.append(_("Delete permanently…"), "win.delete")
        menu.append_section(None, danger)
        self.context_menu = Gtk.PopoverMenu(menu_model=menu, has_arrow=False)
        self.context_menu.connect("closed", lambda p: GLib.idle_add(p.unparent))
        return view

    # -- scanning -------------------------------------------------------------
    def scan(self, path):
        self._cancel_scan()  # a stale scan's result is ignored in _scan_done
        self.scanner = scanner = Scanner(path, one_filesystem=self.start_page.one_filesystem)
        self.scan_page.start(scanner.path)
        self.pages.set_visible_child_name("scan")
        self._update_actions()
        threading.Thread(target=self._scan_thread, args=(scanner,), daemon=True).start()
        GLib.timeout_add(100, self._scan_progress, scanner)

    def _scan_thread(self, scanner):
        try:
            root, error = scanner.run(), None
        except OSError as exc:
            root, error = None, exc
        GLib.idle_add(self._scan_done, scanner, root, error)

    def _scan_progress(self, scanner):
        if scanner is not self.scanner or self.pages.get_visible_child_name() != "scan":
            return GLib.SOURCE_REMOVE
        self.scan_page.update(scanner.bytes, scanner.files, scanner.current)
        return GLib.SOURCE_CONTINUE

    def _scan_done(self, scanner, root, error):
        if scanner is not self.scanner:
            return
        self.scanner = None
        if root is None:  # cancelled or failed: back to where we were
            self.pages.set_visible_child_name("results" if self.root else "start")
            if error is not None:
                self.toast(str(error))
            return
        # Rescanning the same folder keeps the current selection if it still exists.
        same = self.root is not None and self.root.path() == root.path()
        target = _find(root, self.selected.path()) if same and self.selected else root
        self.root = root
        if not same:
            self.freed = 0
        self.columns.set_root(root)
        self.pages.set_visible_child_name("results")
        self.columns.reveal(target)
        if scanner.errors:
            self.toast(_("{n} folders could not be read").format(n=scanner.errors))

    def _cancel_scan(self):
        if self.scanner is not None:
            self.scanner.cancel()

    def _new_scan(self):
        self._cancel_scan()
        self.start_page.refresh()
        self.pages.set_visible_child_name("start")
        self._update_actions()

    def _choose_folder(self):
        dialog = Gtk.FileDialog(initial_folder=Gio.File.new_for_path(GLib.get_home_dir()))

        def chosen(dialog, result):
            try:
                folder = dialog.select_folder_finish(result)
            except GLib.Error:
                return  # dismissed
            if folder and folder.get_path():
                self.scan(folder.get_path())
        dialog.select_folder(self, None, chosen)

    def _on_drop(self, _target, value, _x, _y):
        for file in value.get_files():
            path = file.get_path()
            if path and os.path.isdir(path):
                self.scan(path)
                return True
        return False

    # -- selection ----------------------------------------------------------
    def _on_select(self, node):
        self.selected = node
        self.inspector.show(self.root, node)
        self._update_title()
        self._update_actions()

    def _navigate(self, node):
        self.columns.reveal(node)

    def _on_activate(self, node):
        if node.is_dir:
            self.columns.reveal(node.children[0] if node.children else node)
        else:
            self._open()

    def _on_context_menu(self, widget, x, y):
        if self.context_menu.get_parent() is not None:
            self.context_menu.unparent()
        self.context_menu.set_parent(widget)
        rectangle = Gdk.Rectangle()
        rectangle.x, rectangle.y, rectangle.width, rectangle.height = int(x), int(y), 1, 1
        self.context_menu.set_pointing_to(rectangle)
        self.context_menu.popup()

    def _up(self):
        if self.selected is not None and self.selected.parent is not None:
            self.columns.reveal(self.selected.parent)

    def _update_title(self):
        if self.root is None:
            return
        subtitle = f"{size_text(self.root.size)} · " + _("{n} files").format(n=f"{self.root.count:n}")
        if self.freed:
            subtitle += " · " + _("freed {size}").format(size=size_text(self.freed))
        self.title.set_title(self.root.path())
        self.title.set_subtitle(subtitle)

    def _update_actions(self):
        on_results = self.pages.get_visible_child_name() == "results"
        has = on_results and self.selected is not None
        removable = has and not self.busy and self.selected.parent is not None
        for name, enabled in (("trash", removable), ("delete", removable),
                              ("open", has), ("show-in-folder", has), ("copy-path", has),
                              ("up", has and self.selected.parent is not None),
                              ("rescan", on_results and not self.busy),
                              ("rescan-folder", has and not self.busy),
                              ("new-scan", on_results)):
            self.lookup_action(name).set_enabled(enabled)

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text), timeout=4))

    # -- actions on the selection ----------------------------------------------
    def _file(self):
        return Gio.File.new_for_path(self.selected.path())

    def _open(self):
        launcher = Gtk.FileLauncher.new(self._file())
        launcher.launch(self, None, self._launched, launcher.launch_finish)

    def _show_in_folder(self):
        launcher = Gtk.FileLauncher.new(self._file())
        launcher.open_containing_folder(self, None, self._launched,
                                        launcher.open_containing_folder_finish)

    def _launched(self, _launcher, result, finish):
        try:
            finish(result)
        except GLib.Error as exc:
            if not exc.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                self.toast(exc.message)

    def _copy_path(self):
        self.get_clipboard().set_text(self.selected.path())
        self.toast(_("Path copied"))

    def _set_busy(self, busy):
        self.busy = busy
        self._update_actions()

    def _trash(self):
        node = self.selected
        if node is None or node.parent is None or self.busy:
            return
        self._set_busy(True)
        self._file().trash_async(GLib.PRIORITY_DEFAULT, None, self._trashed, node)

    def _trashed(self, file, result, node):
        self._set_busy(False)
        try:
            file.trash_finish(result)
        except GLib.Error as exc:
            self._ask_delete(node, _("Could not move to trash"), exc.message)
            return
        self._removed(node, _("Moved “{name}” to trash ({size})"))

    def _confirm_delete(self):
        node = self.selected
        if node is None or node.parent is None or self.busy:
            return
        self._ask_delete(node, _("Delete “{name}” permanently?").format(name=node.name))

    def _ask_delete(self, node, heading, reason=None):
        body = _("{size} in {n} files will be removed. This cannot be undone.").format(
            size=size_text(node.size), n=f"{node.count:n}")
        if reason:
            body = f"{reason}.\n\n{body}"
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete permanently"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "delete" and self._delete(node))
        dialog.present(self)

    def _delete(self, node):
        self._set_busy(True)
        path = node.path()

        def work():
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    os.remove(path)
                except OSError:
                    pass
            GLib.idle_add(done, not os.path.lexists(path))

        def done(ok):
            self._set_busy(False)
            if ok:
                self._removed(node, _("Deleted “{name}” ({size})"))
            else:
                self.toast(_("Some items could not be deleted"))
                if node.is_dir:  # partly deleted: look again at what is left
                    self._rescan_node(node)
        threading.Thread(target=work, daemon=True).start()

    def _removed(self, node, message):
        parent = node.parent
        if parent is None:  # already gone from the tree
            return
        self.freed += node.size
        self.toast(message.format(name=node.name, size=size_text(node.size)))
        detach(node)
        self._rebuild(parent)

    def _rescan_folder(self):
        node = self.selected
        self._rescan_node(node if node.is_dir else node.parent)

    def _rescan_node(self, node):
        if node.parent is None:
            self.scan(node.path())
            return
        self._set_busy(True)
        old_size = node.size
        path = node.path()

        def work():
            try:
                fresh, error = Scanner(path, self.start_page.one_filesystem).run(), None
            except OSError as exc:
                fresh, error = None, exc
            GLib.idle_add(done, fresh, error)

        def done(fresh, error):
            self._set_busy(False)
            parent = node.parent
            if parent is None:
                return
            if fresh is None:
                if os.path.lexists(path):  # still there, just unreadable
                    self.toast(str(error))
                    return
                self.freed += node.size  # the folder itself is gone
                detach(node)
                self._rebuild(parent)
                return
            replace(node, fresh)
            self.freed += max(0, old_size - fresh.size)
            self._rebuild(fresh)
        threading.Thread(target=work, daemon=True).start()

    def _rebuild(self, select):
        """Rebuild the views after the tree changed; select `select`."""
        self.inspector.refresh()
        self.columns.set_root(self.root)
        self.columns.reveal(select)


def _find(root, path):
    """The node for `path` in the tree under `root`, or its nearest ancestor."""
    relative = os.path.relpath(path, root.path())
    node = root
    if relative == os.curdir:
        return node
    for part in relative.split(os.sep):
        child = next((c for c in node.children or () if c.name == part), None)
        if child is None:
            break
        node = child
    return node
