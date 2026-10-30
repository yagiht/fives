"""
sketch.py - the FIVES sketch window: a notes page you draw on, or a PDF you mark up.

You can run it on its own to try it:      python sketch.py            (a blank page)
                                          python sketch.py lecture.pdf (mark up a PDF)
eyes.py also starts it for you. Tap the draw hotkey (DRAW_TOGGLE_HOTKEY in config.py, Cmd+Esc by default): the window opens and draw mode turns on.
Tap it again (or press CLOSE) to put it away. Your page stays as you left it.

Drawing (hold a pen key, your hand points):
  Option   plain pen              Control   pen that snaps: hold still at the end of a stroke and
                                            a wobbly line / circle / triangle / rectangle becomes clean
  Everything is smoothed a little as you draw. Buttons are clicked by tapping the pen key over them.

Your original PDF is never changed. SAVE writes a marked-up copy into ~/Documents/FIVES Notes.
SHARE saves, then shows the file in Finder (right-click it > Share > AirDrop / Messages / Mail).

Controlled by eyes.py through stdin, one command per line:
  show | hide | toggle | quit | snap 1 | snap 0 | open /path/to/file.pdf
It prints "closed" when you press CLOSE, so eyes.py can turn draw mode off too.
"""

import os
import subprocess
import sys
import threading
import time

import sketch_logic as L

try:
    import config
except Exception:                                   # run on its own without the rest: use defaults
    config = None


def setting(name, default):
    return getattr(config, name, default) if config is not None else default


# ---- look (tweak freely) ---------------------------------------------------------------------------
BG_ALPHA = 0.88            # how dark the window is. Lower = see more of what's behind it (0.5 to 1.0)
GLOW = 1.0                 # neon glow strength. 0 = off
FOLDER = setting("SKETCH_FOLDER", "~/Documents/FIVES Notes")
AUTOSAVE = setting("SKETCH_AUTOSAVE", True)         # save the marked-up copy whenever you put the window away
CLICK_AWAY = setting("SKETCH_CLICK_AWAY", True)     # click anywhere outside the window = put it away (like a popover)
HOLD_SECONDS = setting("SNAP_QUICK_SECONDS", 0.1)
HOLD_RADIUS = setting("SNAP_QUICK_RADIUS", 8)
MIN_LENGTH = setting("SNAP_MIN_LENGTH", 60)
SMOOTH_PASSES = setting("SKETCH_SMOOTH_PASSES", 2)  # more = calmer lines (0 to 5)
LIVE_FOLLOW = setting("SKETCH_LIVE_FOLLOW", 0.6)    # 1 = ink follows the pointer exactly; lower = calmer
DARK = setting("SKETCH_DARK", True)                 # dark mode: pages shown black with light ink (saved PDFs stay normal)
_SYMBOLS = {"cmd": "⌘", "ctrl": "⌃", "alt": "⌥", "option": "⌥", "shift": "⇧", "esc": "⎋", "space": "SPACE"}
CLOSE_KEYS = "".join(_SYMBOLS.get(k, k.upper()) for k in (setting("DRAW_TOGGLE_HOTKEY", ["cmd", "esc"]) or ["cmd", "esc"]))
CUT = 34                                            # cut-off corner size (design units)
BLUE = (0.24, 0.55, 1.0)
PALE = (0.55, 0.83, 1.0)
WHITE = (0.91, 0.93, 0.95)
GREY = (0.55, 0.59, 0.66)
INK = (0.02, 0.04, 0.08)
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


class State:
    nb = None                  # the Notebook
    page = 0
    view = None                # L.View
    tool = "ink"               # ink | snap | hilite | erase
    color_i = 0
    width_i = 1
    key_snap = False           # eyes.py says the snap pen key is the one being held
    pen = None
    mode = None                # what the current mouse press is doing: "ink" | "erase" | "button" | None
    hover = None
    flash = ("", 0.0)
    scale = 1.0                # window width / design width
    images = {}                # drawn page pictures: (version, page, px) -> NSImage
    opening = False
    visible = False
    drag_from = None           # moving / resizing the window: (pointer, frame) when the drag began


S = State()


def shape_points(w=L.W, h=L.H, cut=CUT, scale=1.0):
    return [(0, 0), ((w - cut) * scale, 0), (w * scale, cut * scale), (w * scale, h * scale),
            (cut * scale, h * scale), (0, (h - cut) * scale)]


def flash(text, seconds=1.6):
    S.flash = (text, time.monotonic() + seconds)


def goto(i):
    i = max(0, min(S.nb.count - 1, i))
    if i != S.page or S.view is None:
        S.page = i
        S.view = L.View(*S.nb.page_size(i))


def doc_name():
    return os.path.basename(S.nb.source) if S.nb.source else "NEW NOTEBOOK"


def snapping_now():
    return S.tool == "snap" or (S.tool == "ink" and S.key_snap)


def palette():
    return L.DARK_INK_COLORS if DARK else L.INK_COLORS


def screen_color(c, alpha=1.0):
    """Saved colour <-> what you see. In dark mode solid ink is light/dark-swapped (the swap undoes itself),
    so white ink on the black screen saves as black ink on the white PDF. Highlighter stays yellow."""
    return L.flip_light(c) if (DARK and alpha >= 1.0) else c


def pen_look():
    """(color as seen on screen, width in page points, alpha) for the current tool."""
    if S.tool == "hilite":
        return L.HILITE_COLOR, L.HILITE_WIDTH, L.HILITE_ALPHA
    return palette()[S.color_i], L.WIDTHS[S.width_i], 1.0


def save(reveal=False):
    try:
        path = S.nb.save()
        flash("SAVED  " + os.path.basename(path), 2.2)
        if reveal and sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        return path
    except Exception as e:
        print("sketch: couldn't save:", e)
        flash("COULDN'T SAVE: " + str(e)[:40], 3.0)
        return None


def open_pdf(path):
    try:
        S.nb.open_pdf(path)
        S.page = -1
        goto(0)
        flash("OPENED  " + os.path.basename(path), 2.0)
        return True
    except Exception as e:
        print("sketch: couldn't open:", e)
        flash("COULDN'T OPEN: " + str(e)[:40], 3.0)
        return False


def press_button(name, controller):
    """Run what a button does. Returns True if the picture changed."""
    nb = S.nb
    if name.startswith("tool:"):
        S.tool = name[5:]
    elif name.startswith("color:"):
        S.color_i = int(name[6:])
        if S.tool in ("erase", "hilite"):
            S.tool = "ink"
    elif name == "width:-":
        S.width_i = max(0, S.width_i - 1)
    elif name == "width:+":
        S.width_i = min(len(L.WIDTHS) - 1, S.width_i + 1)
    elif name == "undo":
        i = nb.undo()
        if i is not None:
            goto(i)
    elif name == "prev":
        goto(S.page - 1)
    elif name == "next":
        goto(S.page + 1)
    elif name == "newpage":
        goto(nb.add_page_after(S.page))
        flash("NEW PAGE  %d" % (S.page + 1))
    elif name == "zoom:+":
        S.view.zoom_by(1)
    elif name == "zoom:-":
        S.view.zoom_by(-1)
    elif name == "zoom:fit":
        S.view.zoom_fit()
    elif name == "save":
        save()
    elif name == "share":
        save(reveal=True)
    elif name == "open":
        controller.choosePDF()
    elif name == "close":
        controller.hide()
        print("closed", flush=True)                 # tells eyes.py to leave draw mode too
    return True


def main() -> None:
    from AppKit import (NSApplication, NSBackingStoreBuffered, NSBezierPath, NSColor, NSFont, NSMakeRect,
                        NSObject, NSPanel, NSScreen, NSView, NSVisualEffectView, NSAppearance, NSTrackingArea,
                        NSString, NSURL, NSZeroRect, NSFontAttributeName, NSForegroundColorAttributeName,
                        NSKernAttributeName, NSAffineTransform, NSGraphicsContext, NSImage, NSShadow, NSEvent)
    from Foundation import NSData, NSTimer
    from PyObjCTools import AppHelper
    import signal
    import objc

    try:                                   # the HUD font that eyes.py uses
        from CoreText import CTFontManagerRegisterFontsForURL, kCTFontManagerScopeProcess
        for name in ("Rajdhani-Medium.ttf", "Rajdhani-Bold.ttf"):
            CTFontManagerRegisterFontsForURL(NSURL.fileURLWithPath_(os.path.join(FONT_DIR, name)),
                                             kCTFontManagerScopeProcess, None)
    except Exception:
        pass

    S.nb = L.Notebook(FOLDER)
    S.view = L.View(*S.nb.page_size(0))
    S.pen = L.Pen(HOLD_SECONDS, HOLD_RADIUS, MIN_LENGTH, SMOOTH_PASSES, LIVE_FOLLOW)
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pdf"):
        open_pdf(sys.argv[1])

    # ---- small drawing helpers (everything is drawn in design units; the view scales them) -----------
    def font(size, bold=False):
        f = NSFont.fontWithName_size_("Rajdhani-Bold" if bold else "Rajdhani-Medium", size)
        return f or (NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))

    def color(c, a=1.0):
        return NSColor.colorWithSRGBRed_green_blue_alpha_(c[0], c[1], c[2], a)

    def attrs_for(size, c=None, bold=False, kern=1.5, alpha=1.0):
        a = {NSFontAttributeName: font(size, bold), NSKernAttributeName: kern}
        if c is not None:
            a[NSForegroundColorAttributeName] = color(c, alpha)
        return a

    def glow_on(radius, c=BLUE, alpha=0.9):
        NSGraphicsContext.saveGraphicsState()
        sh = NSShadow.alloc().init()
        sh.setShadowOffset_((0, 0))
        sh.setShadowBlurRadius_(radius * GLOW * S.scale)
        sh.setShadowColor_(color(c, min(1.0, alpha * GLOW)))
        sh.set()

    def glow_off():
        NSGraphicsContext.restoreGraphicsState()

    def text(s, x, y, size, c, bold=False, kern=1.5, alpha=1.0, glow=0):
        """Draw text with its top-left at (x, y)."""
        if glow and GLOW > 0:
            glow_on(glow)
        NSString.stringWithString_(s).drawAtPoint_withAttributes_((x, y), attrs_for(size, c, bold, kern, alpha))
        if glow and GLOW > 0:
            glow_off()

    def text_width(s, size, bold=False, kern=1.5):
        return NSString.stringWithString_(s).sizeWithAttributes_(attrs_for(size, None, bold, kern)).width

    def centered(s, rect, size, c, bold=True, kern=2.5, alpha=1.0):
        w = text_width(s, size, bold, kern)
        text(s, rect[0] + (rect[2] - w) / 2, rect[1] + (rect[3] - size * 1.15) / 2, size, c, bold, kern, alpha)

    def line(x0, y0, x1, y1, c, width=1.0, alpha=1.0, glow=0):
        if glow and GLOW > 0:
            glow_on(glow)
        p = NSBezierPath.bezierPath()
        p.moveToPoint_((x0, y0))
        p.lineToPoint_((x1, y1))
        p.setLineWidth_(width)
        color(c, alpha).set()
        p.stroke()
        if glow and GLOW > 0:
            glow_off()

    def box(rect, fill=None, stroke=None, width=1.0, fill_alpha=1.0, stroke_alpha=1.0, glow=0):
        if glow and GLOW > 0:
            glow_on(glow)
        r = NSMakeRect(*rect)
        if fill is not None:
            color(fill, fill_alpha).set()
            NSBezierPath.fillRect_(r)
        if stroke is not None:
            color(stroke, stroke_alpha).set()
            p = NSBezierPath.bezierPathWithRect_(r)
            p.setLineWidth_(width)
            p.stroke()
        if glow and GLOW > 0:
            glow_off()

    def poly_path(points, scale=1.0, close=True):
        p = NSBezierPath.bezierPath()
        for i, (x, y) in enumerate(points):
            (p.moveToPoint_ if i == 0 else p.lineToPoint_)((x * scale, y * scale))
        if close:
            p.closePath()
        return p

    def poly(points, fill=None, stroke=None, width=1.0, fill_alpha=1.0, stroke_alpha=1.0, glow=0):
        if glow and GLOW > 0:
            glow_on(glow)
        p = poly_path(points)
        if fill is not None:
            color(fill, fill_alpha).set()
            p.fill()
        if stroke is not None:
            color(stroke, stroke_alpha).set()
            p.setLineWidth_(width)
            p.stroke()
        if glow and GLOW > 0:
            glow_off()

    def chamfer(rect, c=6):
        x, y, w, h = rect
        return [(x + c, y), (x + w, y), (x + w, y + h - c), (x + w - c, y + h), (x, y + h), (x, y + c)]

    def ink_line(points, c, width, alpha=1.0):
        """A pen stroke: round ends and joins."""
        if not points:
            return
        p = poly_path(points, close=False)
        p.setLineWidth_(max(0.6, width))
        p.setLineCapStyle_(1)
        p.setLineJoinStyle_(1)
        color(c, alpha).set()
        p.stroke()

    def point_in(view, event):
        """Where a mouse event landed, in design units (top-left origin, window size divided out)."""
        p = view.convertPoint_fromView_(event.locationInWindow(), None)
        s = view.bounds().size.width / L.W
        return (p.x / s, p.y / s)

    def mouse_at():
        p = NSEvent.mouseLocation()                  # screen points, bottom-left origin (works for FIVES's pen too)
        return (p.x, p.y)

    def page_image(px):
        key = (S.nb.version, S.page, round(px, 2), DARK)
        img = S.images.get(key)
        if img is None:
            raw = S.nb.render(S.page, px, dark=DARK)
            img = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(raw, len(raw)))
            if len(S.images) > 6:
                S.images.pop(next(iter(S.images)))
            S.images[key] = img
        return img

    # ---- the window's contents -------------------------------------------------------------------------
    class SketchView(NSView):
        def isFlipped(self):                    # so (0, 0) is the top-left, like the layout numbers
            return True

        def acceptsFirstMouse_(self, event):    # a click works even though the window isn't "active"
            return True

        def updateTrackingAreas(self):
            objc.super(SketchView, self).updateTrackingAreas()
            for area in list(self.trackingAreas()):
                self.removeTrackingArea_(area)
            area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(self.bounds(), 0x01 | 0x02 | 0x80 | 0x200, self, None)
            self.addTrackingArea_(area)

        def mouseMoved_(self, event):
            name = L.hit(point_in(self, event))
            if name != S.hover:
                S.hover = name
                self.setNeedsDisplay_(True)

        def mouseExited_(self, event):
            S.hover = None
            self.setNeedsDisplay_(True)

        def mouseDown_(self, event):
            try:
                p = point_in(self, event)
                name = L.hit(p)
                S.mode = None
                if name == "page":
                    if S.tool == "erase":
                        S.mode = "erase"
                        S.nb.erase_at(S.page, S.view.to_page(p))
                    else:
                        S.mode = "ink"
                        S.pen.begin(time.monotonic(), p, S.tool in ("ink", "snap"))
                elif name == "grip" or name is None:          # corner = resize, empty frame = move
                    S.mode = "resize" if name == "grip" else "move"
                    S.drag_from = (mouse_at(), controller.frame())
                elif name:
                    S.mode = "button"
                    press_button(name, controller)
            except Exception as e:
                print("sketch click error:", e)
            self.setNeedsDisplay_(True)

        def mouseDragged_(self, event):
            try:
                p = point_in(self, event)
                if S.mode in ("move", "resize") and S.drag_from:
                    (mx, my), start = S.drag_from
                    nx, ny = mouse_at()
                    screen = controller.screen()
                    if S.mode == "move":
                        controller.set_frame(L.moved_frame(start, nx - mx, ny - my, screen))
                    else:
                        controller.set_frame(L.resized_frame(start, nx - mx, ny - my, screen), resized=True)
                    return
                if S.mode == "ink":
                    S.pen.move(time.monotonic(), p)
                elif S.mode == "erase":
                    S.nb.erase_at(S.page, S.view.to_page(p))
            except Exception as e:
                print("sketch drag error:", e)
            self.setNeedsDisplay_(True)

        def mouseUp_(self, event):
            try:
                if S.mode in ("move", "resize"):
                    S.drag_from = None
                    controller.report_frame()
                if S.mode == "ink":
                    pts = S.pen.end(S.view.to_page)
                    if pts:
                        c, w, a = pen_look()
                        S.nb.add_stroke(S.page, L.Stroke(pts, screen_color(c, a), w, a))
            except Exception as e:
                print("sketch pen-up error:", e)
            S.mode = None
            self.setNeedsDisplay_(True)

        def scrollWheel_(self, event):
            try:
                s = self.bounds().size.width / L.W
                S.view.scroll(event.scrollingDeltaX() / s, event.scrollingDeltaY() / s)
            except Exception as e:
                print("sketch scroll error:", e)
            self.setNeedsDisplay_(True)

        # drag a PDF from Finder onto the window
        def draggingEntered_(self, sender):
            return 1

        def prepareForDragOperation_(self, sender):
            return True

        def performDragOperation_(self, sender):
            try:
                files = sender.draggingPasteboard().propertyListForType_("NSFilenamesPboardType") or []
                for f in files:
                    if str(f).lower().endswith(".pdf"):
                        open_pdf(str(f))
                        self.setNeedsDisplay_(True)
                        return True
            except Exception as e:
                print("sketch drop error:", e)
            return False

        def drawRect_(self, dirty):
            try:
                scale = self.bounds().size.width / L.W
                S.scale = scale
                NSGraphicsContext.saveGraphicsState()
                t = NSAffineTransform.transform()
                t.scaleBy_(scale)
                t.concat()
                poly_path(shape_points()).addClip()              # nothing is drawn in the cut-off corners
                draw()
                NSGraphicsContext.restoreGraphicsState()
            except Exception as e:                 # a drawing slip must never kill the window
                print("sketch draw error:", e)

    def draw_page():
        view, nb = S.view, S.nb
        ox, oy = view.origin()
        s = view.scale
        rect = (ox, oy, view.pw * s, view.ph * s)
        NSGraphicsContext.saveGraphicsState()
        NSBezierPath.clipRect_(NSMakeRect(*L.VIEW_RECT))
        glow_on(16, BLUE, 0.35)
        box(rect, fill=tuple(v / 255 for v in L.DARK_PAPER_RGB) if DARK else (0.96, 0.97, 0.98))
        glow_off()
        try:
            img = page_image(min(4.0, max(0.5, s * S.scale * 2.0)))   # capped so zooming in stays quick
            img.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(NSMakeRect(*rect), NSZeroRect, 2, 1.0, True, None)
        except Exception as e:
            print("sketch: couldn't draw the page:", e)
        for st in nb.strokes[S.page]:
            ink_line([view.to_view(q) for q in st.pts], screen_color(st.color, st.alpha), st.width * s, st.alpha)
        if S.pen.active:
            c, w, a = pen_look()
            ink_line(S.pen.shown(), c, w * s, a)
        NSGraphicsContext.restoreGraphicsState()

    def button(name, label, primary=False, active=False):
        rect = L.RECTS[name]
        hov = S.hover == name
        hot = primary or active or hov
        poly(chamfer(rect, 5), fill=BLUE, fill_alpha=0.95 if (primary and not hov) else (0.45 if hov else (0.26 if active else 0.06)),
             stroke=BLUE, width=1.4 if hot else 1.0, stroke_alpha=1.0 if hot else 0.5, glow=5 if hot else 0)
        col = INK if (primary and not hov) else (WHITE if hot else PALE)
        centered(label, rect, 12.5, col, True, 2.5)

    def draw():
        nb = S.nb
        box((0, 0, L.W, L.H), fill=INK, fill_alpha=BG_ALPHA)
        for gx in range(0, L.W + 1, 32):
            line(gx, 0, gx, L.H, BLUE, 0.5, 0.05)
        for gy in range(0, L.H + 1, 32):
            line(0, gy, L.W, gy, BLUE, 0.5, 0.05)
        for k in ((24, 24, 1, 1), (L.W - 24, 24, -1, 1), (24, L.H - 24, 1, -1), (L.W - 24, L.H - 24, -1, -1)):
            line(k[0], k[1], k[0] + 40 * k[2], k[1], WHITE, 1.6, 0.7)
            line(k[0], k[1], k[0], k[1] + 40 * k[3], WHITE, 1.6, 0.7)
        poly(shape_points(), stroke=BLUE, width=1.5, stroke_alpha=0.85, glow=8)

        # --- title
        box((48, 36, 4, 36), fill=BLUE, glow=6)
        text("FIVES  //  SKETCH", 64, 33, 22, WHITE, True, 6.0, 1.0, glow=6)
        info = "%s  ·  PAGE %d / %d  ·  %s" % (doc_name().upper(), S.page + 1, nb.count, "UNSAVED" if nb.dirty else "SAVED")
        text(info[:70], 66, 58, 11, GREY, False, 2.4)

        for name, label, primary in (("open", "OPEN PDF", False), ("newpage", "+ PAGE", False), ("save", "SAVE", True),
                                     ("share", "SHARE", False), ("close", "CLOSE", False)):
            button(name, label, primary=primary)

        # --- the page and its frame
        draw_page()
        vx, vy, vw, vh = L.VIEW_RECT
        for cx, cy, dx, dy in ((vx, vy, 1, 1), (vx + vw, vy, -1, 1), (vx, vy + vh, 1, -1), (vx + vw, vy + vh, -1, -1)):
            line(cx, cy, cx + 16 * dx, cy, BLUE, 2, 1.0, glow=3)
            line(cx, cy, cx, cy + 16 * dy, BLUE, 2, 1.0, glow=3)
        # scroll bar on the right: where you are on the page
        page_h = S.view.ph * S.view.scale
        if page_h > vh + 1:
            top = (vy - S.view.origin()[1]) / page_h
            bx = vx + vw + 10
            line(bx, vy, bx, vy + vh, GREY, 2, 0.25)
            line(bx, vy + top * vh, bx, vy + (top + vh / page_h) * vh, BLUE, 3, 1.0, glow=4)

        # --- toolbar
        poly(chamfer(L.PILL, 8), fill=INK, fill_alpha=0.92, stroke=GREY, width=1.0, stroke_alpha=0.5)
        button("tool:ink", "INK", active=S.tool == "ink")
        button("tool:snap", "SNAP", active=S.tool == "snap")
        button("tool:hilite", "HILITE", active=S.tool == "hilite")
        button("tool:erase", "ERASE", active=S.tool == "erase")
        for i in range(4):
            r = L.RECTS["color:%d" % i]
            box((r[0] + 4, r[1] + 8, r[2] - 8, r[3] - 16), fill=palette()[i])
            if S.color_i == i and S.tool in ("ink", "snap"):
                box((r[0] + 1, r[1] + 5, r[2] - 2, r[3] - 10), stroke=WHITE, width=1.6)
            elif S.hover == "color:%d" % i:
                box((r[0] + 1, r[1] + 5, r[2] - 2, r[3] - 10), stroke=PALE, width=1.0, stroke_alpha=0.7)
        for name, sign in (("width:-", "-"), ("width:+", "+")):
            button(name, "")
            r = L.RECTS[name]
            cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
            line(cx - 6, cy, cx + 6, cy, WHITE, 1.8)
            if sign == "+":
                line(cx, cy - 6, cx, cy + 6, WHITE, 1.8)
        button("undo", "UNDO")
        for name, sign in (("prev", -1), ("next", 1)):
            button(name, "")
            r = L.RECTS[name]
            cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
            poly([(cx - 5 * sign, cy - 7), (cx + 5 * sign, cy), (cx - 5 * sign, cy + 7)], fill=WHITE)
        for name, sign in (("zoom:-", "-"), ("zoom:+", "+")):
            button(name, "")
            r = L.RECTS[name]
            cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
            line(cx - 6, cy, cx + 6, cy, WHITE, 1.8)
            if sign == "+":
                line(cx, cy - 6, cx, cy + 6, WHITE, 1.8)
        button("zoom:fit", "FIT", active=S.view.zoom_i == 0)

        # --- status line: keys, width and zoom
        status = "⌥ PEN  (TAP = CLICK)      ⌃ SNAP PEN      " + CLOSE_KEYS + " CLOSE        WIDTH %.1f    ZOOM %.1fx" % (L.WIDTHS[S.width_i], L.ZOOMS[S.view.zoom_i])
        w = text_width(status, 11, False, 2.4)
        text(status, (L.W - w) / 2, 772, 11, GREY, False, 2.4)

        # --- resize grip in the bottom-right corner
        gx, gy, gw, gh = L.GRIP
        hot = S.hover == "grip" or S.mode == "resize"
        for d in (14, 26, 38):
            line(L.W - 10 - d, L.H - 10, L.W - 10, L.H - 10 - d, BLUE if hot else GREY, 1.6, 1.0 if hot else 0.6, glow=4 if hot else 0)

        # --- a short message in the middle of the page area
        msg, until = S.flash
        if msg and time.monotonic() < until:
            w = text_width(msg, 15, True, 3.0) + 40
            r = ((L.W - w) / 2, 112, w, 36)
            poly(chamfer(r, 6), fill=INK, fill_alpha=0.9, stroke=BLUE, width=1.5, glow=8)
            centered(msg, r, 15, WHITE, True, 3.0)

    # ---- the window itself ----------------------------------------------------------------------------
    class Controller(NSObject):
        """Owns the window: show / hide / timer / the file dialog."""

        def init(self):
            self = objc.super(Controller, self).init()
            self.visible = False
            self.outside_monitor = None                 # watches for clicks outside the window (see watch_outside_clicks)
            self.outside_down = False
            return self

        def build(self):
            screen = NSScreen.mainScreen().visibleFrame()
            k = min(0.96 * screen.size.width / L.W, 0.96 * screen.size.height / L.H, 1.4)
            w, h = L.W * k, L.H * k
            x = screen.origin.x + (screen.size.width - w) / 2
            y = screen.origin.y + (screen.size.height - h) / 2
            style = 0 | 128                                              # borderless + non-activating panel
            self.win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, w, h), style, NSBackingStoreBuffered, False)
            win = self.win
            win.setFloatingPanel_(True)
            win.setLevel_(24)                                            # above normal windows, just under the music window
            win.setOpaque_(False)
            win.setBackgroundColor_(NSColor.clearColor())
            win.setHasShadow_(True)
            win.setHidesOnDeactivate_(False)
            win.setBecomesKeyOnlyIfNeeded_(True)
            win.setAcceptsMouseMovedEvents_(True)
            win.setReleasedWhenClosed_(False)
            win.setCollectionBehavior_(1 | 16 | 256)                     # all desktops + over full-screen apps
            self.fx = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
            fx = self.fx
            fx.setMaterial_(13)
            fx.setBlendingMode_(0)
            fx.setState_(1)
            try:
                fx.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark"))
            except Exception:
                pass
            win.setContentView_(fx)
            self.view = SketchView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
            self.view.setAutoresizingMask_(18)
            try:
                self.view.registerForDraggedTypes_(["NSFilenamesPboardType"])
            except Exception as e:
                print("sketch: drag-and-drop unavailable:", e)
            fx.addSubview_(self.view)
            self.apply_shape(k)

        def apply_shape(self, k):
            """Give the frosted glass the cut-corner outline (otherwise it stays a plain rectangle)."""
            try:
                def handler(rect):
                    NSColor.whiteColor().set()
                    poly_path(shape_points(scale=k)).fill()
                    return True
                self.fx.setMaskImage_(NSImage.imageWithSize_flipped_drawingHandler_((L.W * k, L.H * k), True, handler))
                self.win.invalidateShadow()
            except Exception as e:
                print("sketch: couldn't shape the glass:", e)

        def frame(self):
            f = self.win.frame()
            return (f.origin.x, f.origin.y, f.size.width, f.size.height)

        def screen(self):
            v = (self.win.screen() or NSScreen.mainScreen()).visibleFrame()
            return (v.origin.x, v.origin.y, v.size.width, v.size.height)

        def set_frame(self, f, resized=False):
            self.win.setFrame_display_(NSMakeRect(*f), True)
            if resized:
                self.apply_shape(f[2] / L.W)
            self.view.setNeedsDisplay_(True)

        def watch_outside_clicks(self):
            """Click outside the window (in any other app) = put it away. A drag that starts outside
            (dragging a PDF in from Finder) doesn't count, and nothing happens while the file picker is open."""
            if not CLICK_AWAY or self.outside_monitor is not None:
                return

            def handler(event):
                try:
                    kind = event.type()
                    if not self.visible or S.opening:
                        self.outside_down = False
                    elif kind == 1:                      # left mouse down, somewhere else
                        self.outside_down = True
                    elif kind == 6:                      # dragged: it's a drag, not a click
                        self.outside_down = False
                    elif kind == 2 and self.outside_down:    # let go: that was a click outside
                        self.outside_down = False
                        AppHelper.callAfter(self.clicked_away)
                except Exception as e:
                    print("sketch: outside-click watcher error:", e)

            try:
                mask = (1 << 1) | (1 << 2) | (1 << 6)    # left mouse down, up, dragged
                self.outside_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, handler)
            except Exception as e:
                print("sketch: can't watch outside clicks:", e)
                self.outside_monitor = None

        def clicked_away(self):
            if self.visible and not S.opening:
                self.hide()
                print("closed", flush=True)             # eyes.py leaves draw mode too

        def report_frame(self):
            """Tell eyes.py where we are, so pointing at us + a palm swipe can put us away."""
            try:
                main_h = NSScreen.screens()[0].frame().size.height
                print("frame %.0f %.0f %.0f %.0f" % L.quartz_frame(self.frame(), main_h), flush=True)
            except Exception as e:
                print("sketch: couldn't report the window frame:", e)

        def show(self):
            S.visible = self.visible = True
            self.win.setAlphaValue_(0.0)
            self.win.orderFrontRegardless()
            self.win.animator().setAlphaValue_(1.0)
            self.view.setNeedsDisplay_(True)
            self.report_frame()
            self.watch_outside_clicks()

        def hide(self):
            if S.pen.active:
                S.pen.end(S.view.to_page)
                S.mode = None
            S.visible = self.visible = False
            S.mode, S.drag_from = None, None
            self.win.orderOut_(None)
            print("hidden", flush=True)
            if AUTOSAVE and S.nb.dirty:
                save()

        def toggle(self):
            self.hide() if self.visible else self.show()

        def choosePDF(self):
            """The file picker is a normal window, so it would hide behind ours: put ours away while it is open."""
            if S.opening or sys.platform != "darwin":
                return
            S.opening = True
            self.win.orderOut_(None)

            def job():
                script = 'POSIX path of (choose file of type {"com.adobe.pdf"} with prompt "Pick a PDF to mark up")'
                path = ""
                try:
                    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
                    path = r.stdout.strip()
                except Exception as e:
                    print("sketch: file picker failed:", e)

                def back():
                    S.opening = False
                    if path:
                        open_pdf(path)
                    if self.visible:
                        self.win.orderFrontRegardless()
                    self.view.setNeedsDisplay_(True)
                AppHelper.callAfter(back)
            threading.Thread(target=job, daemon=True).start()

        def tick_(self, timer):
            if not self.visible:
                return
            try:
                if S.pen.active:
                    S.pen.enabled = snapping_now()          # decided at hold time, so a key message arriving late can't matter
                    name = S.pen.tick(time.monotonic())
                    if name:
                        flash("SNAP  " + name.upper(), 1.0)
                    self.view.setNeedsDisplay_(True)
                elif S.flash[0] and time.monotonic() < S.flash[1] + 0.2:
                    self.view.setNeedsDisplay_(True)
            except Exception as e:
                print("sketch tick error:", e)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)                    # "accessory": no Dock icon, no menu bar of its own
    controller = Controller.alloc().init()
    controller.build()
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.03, controller, "tick:", None, True)

    if "--hidden" not in sys.argv:
        controller.show()

    def commands():
        """eyes.py talks to us through our stdin, one command per line."""
        for raw in sys.stdin:
            word, _, rest = raw.strip().partition(" ")
            word = word.lower()
            if word == "toggle":
                AppHelper.callAfter(controller.toggle)
            elif word == "show":
                AppHelper.callAfter(controller.show)
            elif word == "hide":
                AppHelper.callAfter(controller.hide)
            elif word == "snap":
                S.key_snap = rest.strip() == "1"
            elif word == "open" and rest:
                AppHelper.callAfter(lambda p=rest.strip(): open_pdf(p))
            elif word == "quit":
                break
        AppHelper.callAfter(app.terminate_, None)      # stdin closed = eyes.py is gone: quit too

    if not sys.stdin.isatty():
        threading.Thread(target=commands, daemon=True).start()
    signal.signal(signal.SIGINT, lambda *a: app.terminate_(None))     # Ctrl-C quits (checked every tick)
    app.run()


if __name__ == "__main__":
    main()
