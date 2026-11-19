"""What happened: messages shown in the header bar, and the activity log.

Messages never cover the window: they appear for a few seconds in place of
the header subtitle, and stay in the Activity popover. Destructive actions
(and scans) are also appended to a plain-text file, so there is a record of
what was deleted and when: $XDG_STATE_HOME/janitux/activity.log.
"""

import os

from gi.repository import Gio, GLib, Gtk, Pango

from .i18n import _

MESSAGE_SECONDS = 6


class ActivityLog:
    def __init__(self):
        self.path = os.path.join(GLib.get_user_state_dir(), "janitux", "activity.log")
        self.entries = []        # (GLib.DateTime, icon name, text)
        self.unseen = 0
        self._listeners = []

    def listen(self, callback):
        """callback(entry or None): a new entry, or None when all were seen."""
        self._listeners.append(callback)

    def add(self, icon, text, record=None):
        now = GLib.DateTime.new_now_local()
        entry = (now, icon, text)
        self.entries.append(entry)
        self.unseen += 1
        if record:
            self._write(now, record)
        for callback in self._listeners:
            callback(entry)

    def seen(self):
        self.unseen = 0
        for callback in self._listeners:
            callback(None)

    def _write(self, now, record):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as log:
                log.write(f"{now.format('%Y-%m-%d %H:%M:%S')}  {record}\n")
        except OSError:
            pass  # the log is a courtesy: never fail an action because of it


class HeaderTitle(Gtk.Box):
    """Title and subtitle for a header bar; the subtitle can flash a message."""

    def __init__(self, title=""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.title = Gtk.Label(label=title, css_classes=["title"],
                               ellipsize=Pango.EllipsizeMode.START)
        self.subtitle = Gtk.Label(css_classes=["subtitle"], ellipsize=Pango.EllipsizeMode.END)
        self.icon = Gtk.Image()
        self.message = Gtk.Label(css_classes=["subtitle", "header-message"],
                                 ellipsize=Pango.EllipsizeMode.END)
        flash = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        flash.append(self.icon)
        flash.append(self.message)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               transition_duration=250, interpolate_size=True)
        self.stack.add_named(self.subtitle, "subtitle")
        self.stack.add_named(flash, "message")
        self.append(self.title)
        self.append(self.stack)
        self._timer = 0

    def set_title(self, text):
        self.title.set_label(text)

    def set_subtitle(self, text):
        self.subtitle.set_label(text)
        self.subtitle.set_visible(bool(text))

    def flash(self, icon, text):
        self.icon.set_from_icon_name(icon)
        self.message.set_label(text)
        self.stack.set_visible_child_name("message")
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add_seconds(MESSAGE_SECONDS, self._back)

    def _back(self):
        self._timer = 0
        self.stack.set_visible_child_name("subtitle")
        return GLib.SOURCE_REMOVE


class ActivityButton(Gtk.MenuButton):
    """Header button with the session's activity, and a count of what is new."""

    def __init__(self, log):
        super().__init__(tooltip_text=_("Activity"))
        self.log = log
        self.count = Gtk.Label(css_classes=["activity-count"], halign=Gtk.Align.END,
                               valign=Gtk.Align.START, visible=False, can_target=False)
        badge = Gtk.Overlay(child=Gtk.Image(icon_name="document-open-recent-symbolic"))
        badge.add_overlay(self.count)
        self.set_child(badge)

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        self.list.set_placeholder(Gtk.Label(label=_("Nothing happened yet"),
                                            css_classes=["dim-label"], margin_top=12,
                                            margin_bottom=12))
        scroller = Gtk.ScrolledWindow(child=self.list, propagate_natural_height=True,
                                      max_content_height=420, min_content_width=380,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        open_file = Gtk.Button(label=_("Open the log file"), halign=Gtk.Align.END)
        open_file.add_css_class("flat")
        open_file.connect("clicked", self._open_file)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=6,
                      margin_bottom=6, margin_start=6, margin_end=6)
        box.append(Gtk.Label(label=_("Activity"), xalign=0, css_classes=["heading"]))
        box.append(scroller)
        box.append(open_file)
        popover = Gtk.Popover(child=box)
        popover.connect("show", lambda _p: log.seen())
        self.set_popover(popover)

        for entry in log.entries:
            self._add_row(entry)
        log.listen(self._changed)
        self._changed(None)

    def _changed(self, entry):
        if entry is not None:
            self._add_row(entry)
        self.count.set_label(str(min(self.log.unseen, 99)))
        self.count.set_visible(self.log.unseen > 0)

    def _add_row(self, entry):
        when, icon, text = entry
        row = Gtk.Box(spacing=10, margin_top=8, margin_bottom=8, margin_start=10, margin_end=10)
        row.append(Gtk.Image(icon_name=icon, valign=Gtk.Align.START))
        row.append(Gtk.Label(label=text, xalign=0, hexpand=True, wrap=True,
                             wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=40))
        row.append(Gtk.Label(label=when.format("%H:%M"), valign=Gtk.Align.START,
                             css_classes=["caption", "dim-label", "numeric"]))
        self.list.prepend(row)  # newest first

    def _open_file(self, _button):
        if not os.path.exists(self.log.path):
            return
        launcher = Gtk.FileLauncher.new(Gio.File.new_for_path(self.log.path))
        launcher.launch(self.get_root(), None, None)
