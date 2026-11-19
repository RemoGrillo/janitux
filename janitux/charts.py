"""The two pictures of a folder: a sunburst and a squarified treemap.

Both are plain widgets drawn with GTK's snapshot API (GPU rendered, no
cairo bindings needed). They show a `focus` folder, outline the `selected`
node, report the node under the pointer through `on_hover` and ask to go
somewhere through `on_navigate`.
"""

import math
from dataclasses import dataclass

from gi.repository import Adw, Gdk, Graphene, Gsk, Gtk, Pango

from . import kinds
from .common import display_name, palette, percent, size_text
from .i18n import _
from .scanner import Node

ANIMATION_US = 450_000
UP = object()  # hit-test result for the sunburst's center disc


def rgba(rgb, alpha=1.0):
    color = Gdk.RGBA()
    color.red, color.green, color.blue = rgb[:3]
    color.alpha = alpha
    return color


def rect(x, y, w, h):
    return Graphene.Rect().init(x, y, w, h)


def point(x, y):
    return Graphene.Point().init(x, y)


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Chart(Gtk.Widget):
    def __init__(self, on_navigate, on_hover):
        super().__init__(hexpand=True, vexpand=True)
        self.set_size_request(240, 240)
        self.on_navigate = on_navigate
        self.on_hover = on_hover
        self.focus = None
        self.selected = None
        self.hover = None
        self._layout = None
        self._progress = 1.0
        self._anim_start = None
        self._ticking = False
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda _c, x, y: self._set_hover(self.hit(x, y)))
        motion.connect("leave", lambda _c: self._set_hover(None))
        self.add_controller(motion)
        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.add_controller(click)
        Adw.StyleManager.get_default().connect("notify::dark", lambda *_a: self.queue_draw())

    def show(self, focus, selected):
        if focus is not self.focus:
            self.focus = focus
            self._layout = None
            self.hover = None  # recomputed at the next pointer motion
            self._start_animation()
        self.selected = selected
        self.queue_draw()

    def refresh(self):
        """The tree changed: recompute the layout."""
        self._layout = None
        self.hover = None
        self.queue_draw()

    # -- for subclasses -----------------------------------------------------
    def hit(self, x, y):
        raise NotImplementedError

    def paint(self, snapshot, width, height):
        raise NotImplementedError

    # -- plumbing -----------------------------------------------------------
    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        if self.focus is not None and width > 0 and height > 0:
            self.paint(snapshot, width, height)

    def _set_hover(self, target):
        if target is not self.hover:
            self.hover = target
            self.set_cursor_from_name("pointer" if target is not None else None)
            self.on_hover(target if isinstance(target, Node) else None)
            self.queue_draw()

    def _on_click(self, gesture, _n_press, x, y):
        if gesture.get_current_button() != Gdk.BUTTON_PRIMARY:
            return
        target = self.hit(x, y)
        if target is UP:
            self.on_navigate(self.focus.parent)
        elif target is not None:
            self.on_navigate(target)

    def _start_animation(self):
        if not Gtk.Settings.get_default().get_property("gtk-enable-animations"):
            self._progress = 1.0
            return
        self._progress = 0.0
        self._anim_start = None
        if not self._ticking:
            self._ticking = True
            self.add_tick_callback(self._tick)

    def _tick(self, _widget, clock):
        now = clock.get_frame_time()
        if self._anim_start is None:
            self._anim_start = now
        t = min(1.0, (now - self._anim_start) / ANIMATION_US)
        self._progress = 1 - (1 - t) ** 3  # ease out
        self.queue_draw()
        self._ticking = t < 1.0
        return self._ticking

    def text(self, snapshot, markup, x, y, width, color, center=False):
        """Draw one Pango markup block, middle-ellipsized; return its height."""
        layout = self.create_pango_layout(None)
        layout.set_markup(markup, -1)
        layout.set_width(max(1, int(width * Pango.SCALE)))
        layout.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        if center:
            layout.set_alignment(Pango.Alignment.CENTER)
        return self._draw_layout(snapshot, layout, x, y, color)

    def measure(self, markup):
        layout = self.create_pango_layout(None)
        layout.set_markup(markup, -1)
        return layout.get_pixel_size()[0]

    def number(self, snapshot, markup, x, y, width, color):
        """Draw text that must never be shortened (a size): only if it fits whole.
        Return its width, or 0 when it was left out."""
        layout = self.create_pango_layout(None)
        layout.set_markup(markup, -1)
        text_width = layout.get_pixel_size()[0]
        if text_width > width:
            return 0
        self._draw_layout(snapshot, layout, x, y, color)
        return text_width

    def _draw_layout(self, snapshot, layout, x, y, color):
        snapshot.save()
        snapshot.translate(point(x, y))
        snapshot.append_layout(layout, color)
        snapshot.restore()
        return layout.get_pixel_size()[1]


# ---------------------------------------------------------------------------
# Sunburst
# ---------------------------------------------------------------------------

def _sector(cx, cy, r0, r1, a0, a1):
    """Ring slice between radii r0 < r1 and angles a0 < a1 (clockwise)."""
    def at(r, a):
        return cx + r * math.cos(a), cy + r * math.sin(a)
    mid = (a0 + a1) / 2  # two half arcs: never ambiguous, even at 360°
    b = Gsk.PathBuilder.new()
    b.move_to(*at(r1, a0))
    b.svg_arc_to(r1, r1, 0, False, True, *at(r1, mid))
    b.svg_arc_to(r1, r1, 0, False, True, *at(r1, a1))
    b.line_to(*at(r0, a1))
    b.svg_arc_to(r0, r0, 0, False, False, *at(r0, mid))
    b.svg_arc_to(r0, r0, 0, False, False, *at(r0, a0))
    b.close()
    return b.to_path()


class Sunburst(Chart):
    LEVELS = 5
    MIN_ANGLE = 0.006  # radians; thinner slices are left out
    START = -math.pi / 2  # 12 o'clock

    def _segments(self):
        if self._layout is None:
            segments = []

            def walk(node, depth, a0, a1):
                scale = (a1 - a0) / node.size
                angle = a0
                for child in node.children:
                    sweep = child.size * scale
                    if sweep < self.MIN_ANGLE:
                        break  # children are sorted: all the rest is smaller
                    segments.append((child, depth, angle, angle + sweep))
                    if child.children and depth < self.LEVELS:
                        walk(child, depth + 1, angle, angle + sweep)
                    angle += sweep

            if self.focus.children and self.focus.size > 0:
                walk(self.focus, 1, 0.0, 2 * math.pi)
            levels = max((s[1] for s in segments), default=1)
            self._layout = (segments, max(levels, 3))
        return self._layout

    def _geometry(self):
        width, height = self.get_width(), self.get_height()
        radius = min(width, height) / 2 - 6
        hole = radius * 0.36
        ring = (radius - hole) / self._segments()[1]
        return width / 2, height / 2, hole, ring

    def hit(self, x, y):
        if self.focus is None:
            return None
        cx, cy, hole, ring = self._geometry()
        r = math.hypot(x - cx, y - cy)
        if r < hole:
            return UP if self.focus.parent is not None else None
        depth = int((r - hole) // ring) + 1
        angle = (math.atan2(y - cy, x - cx) - self.START) % (2 * math.pi)
        for node, d, a0, a1 in self._segments()[0]:
            if d == depth and a0 <= angle < a1:
                return node
        return None

    def _lit(self):
        """Predicate: is a node on the hovered branch (ancestor or descendant)?"""
        hover = self.hover
        if not isinstance(hover, Node):
            return lambda node: True
        ancestors = set()
        node = hover
        while node is not None and node is not self.focus:
            ancestors.add(id(node))
            node = node.parent

        def lit(node):
            if id(node) in ancestors:
                return True
            while node is not None and node is not self.focus:
                if node is hover:
                    return True
                node = node.parent
            return False
        return lit

    def paint(self, snapshot, width, height):
        segments, _levels = self._segments()
        cx, cy, hole, ring = self._geometry()
        colors = palette()
        ink = self.get_color()
        sweep_scale = self._progress
        lit = self._lit()
        selected_path = None

        for node, depth, a0, a1 in segments:
            r0 = hole + (depth - 1) * ring + 1
            r1 = hole + depth * ring - 1
            a0, a1 = a0 * sweep_scale, a1 * sweep_scale
            pad = min(0.8 / ((r0 + r1) / 2), (a1 - a0) * 0.2)  # ~2px gap
            path = _sector(cx, cy, r0, r1, self.START + a0 + pad, self.START + a1 - pad)
            alpha = 1.0 - (depth - 1) * 0.09
            if not lit(node):
                alpha *= 0.25
            snapshot.append_fill(path, Gsk.FillRule.WINDING, rgba(colors[node.kind()], alpha))
            if node is self.selected:
                selected_path = path
        if selected_path is not None:
            snapshot.append_stroke(selected_path, Gsk.Stroke.new(2.5), ink)

        # Center disc: the hovered item, or the focus folder itself.
        disc = Gsk.PathBuilder.new()
        disc.add_circle(point(cx, cy), hole - 3)
        snapshot.append_fill(disc.to_path(), Gsk.FillRule.WINDING,
                             rgba((ink.red, ink.green, ink.blue), 0.11 if self.hover is UP else 0.05))
        if self.hover is UP:
            lines = ["<span size='xx-large'>↑</span>", escape(_("Up one level"))]
        else:
            shown = self.hover if isinstance(self.hover, Node) else self.focus
            if shown is self.focus:
                detail = _("{n} files").format(n=f"{shown.count:n}")
            else:
                detail = percent(shown.size, self.focus.size)
            lines = [f"<span size='small' weight='bold'>{escape(display_name(shown))}</span>",
                     f"<span size='large' weight='heavy'>{escape(size_text(shown.size))}</span>",
                     f"<span size='small'>{escape(detail)}</span>"]
        layout = self.create_pango_layout(None)
        layout.set_markup("\n".join(lines), -1)
        text_width = hole * 1.7
        layout.set_width(int(text_width * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        layout.set_alignment(Pango.Alignment.CENTER)
        text_height = layout.get_pixel_size()[1]
        snapshot.save()
        snapshot.translate(point(cx - text_width / 2, cy - text_height / 2))
        snapshot.append_layout(layout, ink)
        snapshot.restore()


# ---------------------------------------------------------------------------
# Treemap
# ---------------------------------------------------------------------------

@dataclass
class Box:
    node: object    # a Node, or None for the "N more items" remainder
    x: float
    y: float
    w: float
    h: float
    container: bool
    rest: int = 0   # how many items were folded into a remainder box


def squarify(values, x, y, w, h):
    """Squarified treemap (Bruls, Huizing, van Wijk 2000).

    `values` must be positive and sorted biggest first; returns one
    (x, y, w, h) rectangle per value, filling the given area.
    """
    rects = []
    total = sum(values)
    if total <= 0 or w <= 0 or h <= 0:
        return [(x, y, 0, 0)] * len(values)
    areas = [v * w * h / total for v in values]
    i, n = 0, len(areas)
    while i < n:
        side = min(w, h)
        s = big = small = areas[i]
        worst = max(side * side * big / (s * s), s * s / (side * side * small))
        j = i + 1
        while j < n:  # grow the row while its worst aspect ratio improves
            a = areas[j]
            s2, big2, small2 = s + a, max(big, a), min(small, a)
            worst2 = max(side * side * big2 / (s2 * s2), s2 * s2 / (side * side * small2))
            if worst2 > worst:
                break
            s, big, small, worst = s2, big2, small2, worst2
            j += 1
        if w >= h:  # the row becomes a column on the left
            thickness, offset = s / h, y
            for a in areas[i:j]:
                rects.append((x, offset, thickness, a / thickness))
                offset += a / thickness
            x, w = x + thickness, w - thickness
        else:       # the row goes along the top
            thickness, offset = s / w, x
            for a in areas[i:j]:
                rects.append((offset, y, a / thickness, thickness))
                offset += a / thickness
            y, h = y + thickness, h - thickness
        i = j
    return rects


def rounded_rect(x, y, w, h, radius):
    rounded = Gsk.RoundedRect()
    rounded.init_from_rect(rect(x, y, w, h), min(radius, w / 2, h / 2))
    return rounded


def _rounded_path(x, y, w, h, radius):
    b = Gsk.PathBuilder.new()
    b.add_rounded_rect(rounded_rect(x, y, w, h, radius))
    return b.to_path()


def _cushion_stops():
    stops = []
    for offset, rgb, alpha in ((0.0, (1, 1, 1), 0.18), (0.5, (1, 1, 1), 0.0), (1.0, (0, 0, 0), 0.16)):
        stop = Gsk.ColorStop()
        stop.offset = offset
        stop.color = rgba(rgb, alpha)
        stops.append(stop)
    return stops


class Treemap(Chart):
    LEVELS = 3          # nesting depth drawn at once
    HEADER = 18         # height of a nested folder's title strip
    MIN_AREA = 40       # px²; smaller items fold into one "N more items" box
    MAX_ITEMS = 400     # per folder
    RADIUS = 4

    def __init__(self, *args):
        super().__init__(*args)
        self._stops = _cushion_stops()

    def _boxes(self):
        size = (self.get_width(), self.get_height())
        if self._layout is None or self._layout[0] != size:
            boxes = []
            self._place(self.focus, 0, 0, size[0], size[1], 0, boxes)
            self._layout = (size, boxes)
        return self._layout[1]

    def _place(self, node, x, y, w, h, depth, out):
        items = [c for c in node.children if c.size > 0]
        total = sum(c.size for c in items)
        if total <= 0 or w < 2 or h < 2:
            return
        px_per_byte = w * h / total
        keep, rest_size, rest_count = [], 0, 0
        for child in items:
            if child.size * px_per_byte >= self.MIN_AREA and len(keep) < self.MAX_ITEMS:
                keep.append(child)
            else:
                rest_size += child.size
                rest_count += 1
        values = [c.size for c in keep] + ([rest_size] if rest_count else [])
        for i, (bx, by, bw, bh) in enumerate(squarify(values, x, y, w, h)):
            if i == len(keep):
                out.append(Box(None, bx, by, bw, bh, False, rest_count))
                continue
            child = keep[i]
            nested = bool(child.children) and depth + 1 < self.LEVELS \
                and bw > 60 and bh > self.HEADER + 30
            out.append(Box(child, bx, by, bw, bh, nested))
            if nested:
                self._place(child, bx + 3, by + self.HEADER, bw - 6, bh - self.HEADER - 3,
                            depth + 1, out)

    def hit(self, x, y):
        if self.focus is None:
            return None
        for box in reversed(self._boxes()):  # deepest boxes come last
            if box.node is not None and box.x <= x < box.x + box.w \
                    and box.y <= y < box.y + box.h:
                return box.node
        return None

    def paint(self, snapshot, width, height):
        colors = palette()
        ink = self.get_color()
        ink_rgb = (ink.red, ink.green, ink.blue)
        p = self._progress
        snapshot.push_opacity(p)
        if p < 1:  # zoom in from slightly smaller while fading in
            scale = 0.94 + 0.06 * p
            snapshot.translate(point(width * (1 - scale) / 2, height * (1 - scale) / 2))
            snapshot.scale(scale, scale)
        outlines = []
        for box in self._boxes():
            x, y, w, h = box.x + 1, box.y + 1, box.w - 2, box.h - 2  # 2px gaps
            if w < 1 or h < 1:
                continue
            node = box.node
            if node is None:
                snapshot.append_fill(_rounded_path(x, y, w, h, self.RADIUS),
                                     Gsk.FillRule.WINDING, rgba(ink_rgb, 0.08))
                if w > 80 and h > 22:
                    label = escape(_("{n} more items").format(n=box.rest))
                    self.text(snapshot, f"<span size='small'>{label}</span>",
                              x + 6, y + 3, w - 12, rgba(ink_rgb, 0.6))
                continue
            kind = node.kind()
            name = escape(node.name)
            size = escape(size_text(node.size))
            if box.container:
                snapshot.append_fill(_rounded_path(x, y, w, h, self.RADIUS),
                                     Gsk.FillRule.WINDING, rgba(colors[kind], 0.16))
                snapshot.push_clip(rect(x, y, w, self.HEADER))
                size_markup = f"<span size='small'>{size}</span>"
                size_width = self.measure(size_markup)
                if size_width + 40 <= w - 12:  # room for the size and some name
                    self.number(snapshot, size_markup, x + w - 6 - size_width, y + 1,
                                size_width, ink)
                    name_width = w - 12 - size_width - 8
                else:
                    name_width = w - 12
                self.text(snapshot, f"<span size='small'><b>{name}</b></span>",
                          x + 6, y + 1, name_width, ink)
                snapshot.pop()
            else:
                snapshot.push_rounded_clip(rounded_rect(x, y, w, h, self.RADIUS))
                snapshot.append_color(rgba(colors[kind]), rect(x, y, w, h))
                # a soft "cushion" so the tiles read as surfaces
                snapshot.append_linear_gradient(rect(x, y, w, h), point(x, y),
                                                point(x + w, y + h), self._stops)
                if w > 60 and h > 36:
                    label_ink = rgba(kinds.INK_ON[kind])
                    used = self.text(snapshot, f"<span size='small'><b>{name}</b></span>",
                                     x + 6, y + 4, w - 12, label_ink)
                    self.number(snapshot, f"<span size='small'>{size}</span>",
                                x + 6, y + 4 + used, w - 12, label_ink)
                snapshot.pop()
            if node is self.selected:
                outlines.insert(0, (x, y, w, h, 0.7))
            if node is self.hover:
                outlines.append((x, y, w, h, 1.0))
        for x, y, w, h, alpha in outlines:
            snapshot.append_stroke(_rounded_path(x + 1, y + 1, w - 2, h - 2, self.RADIUS),
                                   Gsk.Stroke.new(2), rgba(ink_rgb, alpha))
        snapshot.pop()
