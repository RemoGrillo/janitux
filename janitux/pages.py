"""The start page (where to scan) and the scanning page (progress)."""

import os
import re
import threading

from gi.repository import Adw, Gio, GLib, Gtk, Pango

from . import APP_ID
from .activity import ActivityButton, HeaderTitle
from .common import size_text
from .i18n import TAGLINE, _, plural
from .places import measure_trash, mounts, trash_dirs


def _labels():
    """Map device path -> filesystem label, from /dev/disk/by-label."""
    labels = {}
    try:
        for entry in os.scandir("/dev/disk/by-label"):
            label = re.sub(r"\\x([0-9a-f]{2})", lambda m: chr(int(m.group(1), 16)), entry.name)
            labels[os.path.realpath(entry.path)] = label
    except OSError:
        pass
    return labels


def locations():
    """(path, title, subtitle, icon) for the home folder and each mounted disk."""
    home = GLib.get_home_dir()
    found = [(home, _("Home folder"), home, "user-home-symbolic")]
    labels = _labels()
    for device, mount, fstype in mounts():
        real = os.path.realpath(device)
        icon = "media-removable-symbolic" if mount.startswith(("/run/media", "/media")) \
            else "drive-harddisk-symbolic"
        label = labels.get(real)
        subtitle = f"{mount} · {fstype}" if label else f"{fstype} · {real}"
        found.append((mount, label or mount, subtitle, icon))
    return found


def _usage(path):
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    return st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize


def header_with_menu(log, title):
    """Header bar with a title that can flash messages, the activity log and the menu."""
    header = Adw.HeaderBar(title_widget=title)
    menu = Gio.Menu()
    menu.append(_("Empty trash…"), "win.empty-trash")
    about = Gio.Menu()
    about.append(_("About Janitux"), "app.about")
    menu.append_section(None, about)
    header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu))
    header.pack_end(ActivityButton(log))
    return header


class StartPage(Adw.Bin):
    def __init__(self, on_scan, on_choose, log):
        super().__init__()
        view = Adw.ToolbarView()
        self.title = HeaderTitle("Janitux")
        view.add_top_bar(header_with_menu(log, self.title))
        self.set_child(view)
        self.on_scan = on_scan
        self.places = Adw.PreferencesGroup(title=_("Locations"))
        choose = Adw.ActionRow(title=_("Choose a folder…"),
                               subtitle=_("Pick any folder, or drop one on this window"),
                               activatable=True)
        choose.add_prefix(Gtk.Image(icon_name="folder-open-symbolic"))
        choose.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        choose.connect("activated", lambda _r: on_choose())
        self.choose = Adw.PreferencesGroup()
        self.choose.add(choose)
        self.one_fs = Adw.SwitchRow(title=_("Stay on one filesystem"),
                                    subtitle=_("Skip other disks and mounts found inside the folder"),
                                    active=True)
        options = Adw.PreferencesGroup()
        options.add(self.one_fs)

        self.trash = Adw.ActionRow(title=_("Trash"), subtitle=_("Measuring…"))
        self.trash.add_prefix(Gtk.Image(icon_name="user-trash-symbolic"))
        self.empty = Gtk.Button(label=_("Empty…"), action_name="win.empty-trash",
                                valign=Gtk.Align.CENTER, sensitive=False)
        self.empty.add_css_class("destructive-action")
        self.trash.add_suffix(self.empty)
        trash = Adw.PreferencesGroup()
        trash.add(self.trash)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        box.append(self.places)
        box.append(self.choose)
        box.append(trash)
        box.append(options)
        theme = Gtk.IconTheme.get_for_display(self.get_display())
        status = Adw.StatusPage(
            icon_name=APP_ID if theme.has_icon(APP_ID) else "drive-harddisk-symbolic",
            title="Janitux", description=TAGLINE,
            child=Adw.Clamp(maximum_size=600, child=box))
        view.set_content(status)
        self._rows = []
        self.refresh()

    @property
    def one_filesystem(self):
        return self.one_fs.get_active()

    def refresh_trash(self):
        """Measure the trash in the background and show it."""
        self.trash.set_subtitle(_("Measuring…"))

        def measure():
            size, items = measure_trash(trash_dirs())
            GLib.idle_add(show, size, items)

        def show(size, items):
            if items:
                self.trash.set_subtitle(plural(items, "{size} in {n} item", "{size} in {n} items",
                                              size=size_text(size)))
            else:
                self.trash.set_subtitle(_("The trash is empty"))
            self.empty.set_sensitive(items > 0)
        threading.Thread(target=measure, daemon=True).start()

    def refresh(self):
        self.refresh_trash()
        for row in self._rows:
            self.places.remove(row)
        self._rows = []
        for path, title, subtitle, icon in locations():
            row = Adw.ActionRow(title=title, subtitle=subtitle, activatable=True)
            row.add_prefix(Gtk.Image(icon_name=icon))
            usage = _usage(path)
            if usage and usage[0] > 0:
                total, free = usage
                bar = Gtk.LevelBar(value=1 - free / total, width_request=150,
                                   valign=Gtk.Align.CENTER)
                bar.add_css_class("disk-usage")  # keep the default classes
                for name in ("low", "high", "full"):  # those mean "battery level"
                    bar.remove_offset_value(name)
                bar.add_offset_value("roomy", 0.8)   # styled in window.CSS
                bar.add_offset_value("filling", 0.92)
                bar.add_offset_value("crowded", 1.0)
                text = Gtk.Label(label=_("{free} free of {total}").format(
                    free=size_text(free), total=size_text(total)),
                    css_classes=["caption", "dim-label", "numeric"], xalign=1)
                meter = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                                valign=Gtk.Align.CENTER)
                meter.append(bar)
                meter.append(text)
                row.add_suffix(meter)
            row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
            row.connect("activated", lambda _r, p=path: self.on_scan(p))
            self.places.add(row)
            self._rows.append(row)


class ScanPage(Adw.Bin):
    def __init__(self, on_cancel):
        super().__init__()
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar(show_title=False))
        self.set_child(view)
        self.size = Gtk.Label(css_classes=["title-1", "numeric"])
        self.files = Gtk.Label(css_classes=["numeric", "dim-label"])
        self.current = Gtk.Label(css_classes=["caption", "dim-label"],
                                 ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=60)
        cancel = Gtk.Button(label=_("Cancel"), css_classes=["pill"], halign=Gtk.Align.CENTER,
                            margin_top=18)
        cancel.connect("clicked", lambda _b: on_cancel())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for widget in (self.size, self.files, self.current, cancel):
            box.append(widget)
        self.status = Adw.StatusPage(title=_("Investigating…"), child=box)
        if hasattr(Adw, "SpinnerPaintable"):  # libadwaita >= 1.6
            self.status.set_paintable(Adw.SpinnerPaintable.new(self.status))
        else:
            self.status.set_icon_name("content-loading-symbolic")
        view.set_content(self.status)

    def start(self, path):
        self.status.set_description(path)
        self.update(0, 0, path)

    def update(self, size, files, current):
        self.size.set_label(size_text(size))
        self.files.set_label(plural(files, "{n} file", "{n} files"))
        self.current.set_label(current)
