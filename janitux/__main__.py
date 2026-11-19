"""Entry point: `janitux [FOLDER]` or `python3 -m janitux [FOLDER]`."""

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from . import APP_ID, WEBSITE, __version__  # noqa: E402
from .i18n import TAGLINE  # noqa: E402

MIN_GTK = (4, 14)
MIN_ADW = (1, 5)


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.set_option_context_parameter_string("[FOLDER]")

    def do_startup(self):
        Adw.Application.do_startup(self)
        from .window import CSS, SHORTCUTS
        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        display = Gdk.Display.get_default()
        Gtk.StyleContext.add_provider_for_display(display, css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        # Running from a source checkout: find the icon next to the package.
        icons = os.path.join(os.path.dirname(__file__), os.pardir, "data", "icons")
        if os.path.isdir(icons):
            Gtk.IconTheme.get_for_display(display).add_search_path(os.path.abspath(icons))
        Gtk.Window.set_default_icon_name(APP_ID)
        for action, accels in SHORTCUTS.items():
            self.set_accels_for_action(action, accels)
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])
        for name, callback in (("about", self._about), ("quit", lambda: self.quit())):
            action = Gio.SimpleAction(name=name)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)

    def do_activate(self):
        self._window().present()

    def do_open(self, files, _n_files, _hint):
        window = self._window()
        window.present()
        window.scan(files[0].get_path())

    def _window(self):
        from .window import Window
        return self.get_active_window() or Window(self)

    def _about(self):
        Adw.AboutDialog(
            application_name="Janitux", application_icon=APP_ID, version=__version__,
            comments=TAGLINE,
            license_type=Gtk.License.GPL_3_0,
            developer_name="Remo Grillo", website=WEBSITE, issue_url=WEBSITE + "/issues",
        ).present(self.get_active_window())


def main():
    gtk, adw = (Gtk.get_major_version(), Gtk.get_minor_version()), \
        (Adw.get_major_version(), Adw.get_minor_version())
    if gtk < MIN_GTK or adw < MIN_ADW:
        sys.exit(f"janitux needs GTK >= {'.'.join(map(str, MIN_GTK))} and libadwaita >= "
                 f"{'.'.join(map(str, MIN_ADW))} (found {gtk[0]}.{gtk[1]} / {adw[0]}.{adw[1]})")
    return Application().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
