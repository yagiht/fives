"""
panel.py - the FIVES music window: a small translucent window that floats over everything.

You can run it on its own to try it:      python panel.py
eyes.py also starts it for you and sends it "toggle" when you tap the panel hotkey.

Why a separate program: a floating window needs its own macOS "app loop", and the camera window
(OpenCV) has one too. Two in one program fight. As two programs they never meet.

Using it (mouse or pinch, it's all the same to macOS):
  - press PREV / PLAY / NEXT, click the bars to jump around, drag along a bar to scrub
  - drag empty glass to MOVE it, drag the little corner mark at the bottom-right to RESIZE it
  - CLOSE hides it (tap the panel hotkey in eyes.py, or press M in the eyes window, to bring it back)

Spotify itself is controlled by spotify.py (AppleScript). The Spotify app must be open.
"""

import os
import sys
import threading
import time
import urllib.request

import spotify
from panel_logic import CUT, H, MAX_W, MIN_W, W, Layout, clamp_width, ellipsize, fmt_time, frame_points

# ---- look (tweak freely) ---------------------------------------------------------------------------
TINT_ALPHA = 0.36          # how dark the glass is. Lower = see more of Chrome behind it (0.2 to 0.8)
TEXT_ALPHA = 0.80          # how solid the writing is. Lower = more see-through hologram (0.5 to 1.0)
GLOW = 1.0                 # neon glow strength. 0 = off, 1 = normal, 1.6 = very bright
SWEEP = True               # a faint bright line sliding down the window, like a hologram scan
CLOSE_QUITS_SPOTIFY = True # the CLOSE button also closes the Spotify app (the hotkey only hides the window)
MARGIN = 24                # distance from the top-right corner of the screen
BLUE = (0.16, 0.60, 1.0)       # neon 501st blue (the HUD blue, brighter)
PALE = (0.55, 0.83, 1.0)
WHITE = (0.86, 0.95, 1.0)      # cool white
GREY = (0.45, 0.63, 0.82)      # cool blue-grey for quiet labels
INK = (0.02, 0.05, 0.12)
GREEN = (0.239, 1.0, 0.612)    # "hand lock" green, used for PLAYING
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


class State:
    """What the window shows. The poll thread writes it, the drawing code reads it."""
    info = {"state": "closed"}
    polled_at = 0.0
    art = None                 # NSImage of the album cover
    art_url = ""
    hover = None               # name of the button under the pointer
    scale = 1.0                # window size / design size (glow radius follows it)
    refresh = threading.Event()


S = State()


def shown_position() -> float:
    """Where the song is right now: the last known spot plus the time since (smooth between polls)."""
    info = S.info
    pos = info.get("position", 0.0)
    if info.get("state") == "playing":
        pos += time.time() - S.polled_at
    return min(pos, info.get("duration", pos) or pos)


def poll_loop() -> None:
    while True:
        info = spotify.status()
        S.info, S.polled_at = info, time.time()
        url = info.get("art_url", "")
        if url and url != S.art_url:
            S.art_url = url
            threading.Thread(target=load_art, args=(url,), daemon=True).start()
        S.refresh.wait(1.0)
        S.refresh.clear()


def load_art(url: str) -> None:
    try:
        from AppKit import NSImage
        from Foundation import NSData
        raw = urllib.request.urlopen(url, timeout=5).read()
        data = NSData.dataWithBytes_length_(raw, len(raw))
        S.art = NSImage.alloc().initWithData_(data)
    except Exception:
        S.art = None


def do(action: str, value=None) -> None:
    """Run a button's job on a side thread (talking to Spotify takes ~0.1 s; don't freeze the window)."""
    info = S.info
    def job():
        state = info.get("state")
        if state == "closed":
            if action in ("play", "next", "prev"):
                spotify.open_app()                      # only when the Spotify app is really not open
        elif state == "error":
            pass                                        # can't talk to it: the window explains why
        elif action == "play":
            spotify.play_pause()
        elif action == "next":
            spotify.next_track()
        elif action == "prev":
            spotify.previous_track()
        elif action == "seek" and info.get("duration"):
            spotify.seek(value * info["duration"])
        elif action == "volume":
            spotify.set_volume(round(value * 100))
        time.sleep(0.15)
        S.refresh.set()
    # show the effect at once, the real answer arrives with the next poll
    if action == "play" and info.get("state") in ("playing", "paused"):
        S.info = dict(info, state="paused" if info["state"] == "playing" else "playing",
                      position=shown_position())
        S.polled_at = time.time()
    elif action == "volume" and info.get("state") in ("playing", "paused"):
        S.info = dict(info, volume=round(value * 100))
    elif action == "seek" and info.get("duration"):
        S.info = dict(info, position=value * info["duration"])
        S.polled_at = time.time()
    threading.Thread(target=job, daemon=True).start()


def main() -> None:
    from AppKit import (NSApplication, NSBackingStoreBuffered, NSBezierPath, NSColor, NSFont, NSMakeRect,
                        NSObject, NSPanel, NSScreen, NSView, NSVisualEffectView, NSAppearance, NSTrackingArea,
                        NSString, NSURL, NSZeroRect, NSFontAttributeName, NSForegroundColorAttributeName,
                        NSKernAttributeName, NSAffineTransform, NSGraphicsContext, NSEvent, NSImage, NSShadow)
    from Foundation import NSTimer
    from PyObjCTools import AppHelper
    import signal
    import objc

    try:                                   # load the HUD font that eyes.py uses
        from CoreText import CTFontManagerRegisterFontsForURL, kCTFontManagerScopeProcess
        for name in ("Rajdhani-Medium.ttf", "Rajdhani-Bold.ttf"):
            CTFontManagerRegisterFontsForURL(NSURL.fileURLWithPath_(os.path.join(FONT_DIR, name)),
                                             kCTFontManagerScopeProcess, None)
    except Exception:
        pass

    # ---- small drawing helpers (everything is drawn in design units; the view scales them) ---------
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
        """Everything drawn until glow_off() gets a soft neon halo."""
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
        NSString.stringWithString_(s).drawAtPoint_withAttributes_(
            (x, y), attrs_for(size, c, bold, kern, alpha * TEXT_ALPHA))
        if glow and GLOW > 0:
            glow_off()

    def text_width(s, size, bold=False, kern=1.5):
        return NSString.stringWithString_(s).sizeWithAttributes_(attrs_for(size, None, bold, kern)).width

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

    def poly_path(points, scale=1.0):
        p = NSBezierPath.bezierPath()
        for i, (x, y) in enumerate(points):
            (p.moveToPoint_ if i == 0 else p.lineToPoint_)((x * scale, y * scale))
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
        """A rectangle with its top-left and bottom-right corners cut off (armor-plate look)."""
        x, y, w, h = rect
        return [(x + c, y), (x + w, y), (x + w, y + h - c), (x + w - c, y + h), (x, y + h), (x, y + c)]

    def segments(rect, frac, count, on, off_alpha=0.12):
        """A bar made of little blocks, like the HUD's telemetry. The lit blocks glow."""
        x, y, w, h = rect
        step = w / count
        lit = int(round(max(0.0, min(1.0, frac)) * count))
        for i in range(count):
            box((x + i * step, y, step - 1.6, h), fill=BLUE if i >= lit else on, fill_alpha=off_alpha * 1.6 if i >= lit else 0.95)
        if lit:
            glow_on(5)
            for i in range(max(0, lit - 3), lit):         # only the leading blocks need the halo
                box((x + i * step, y, step - 1.6, h), fill=on, fill_alpha=0.95)
            glow_off()

    def icon(kind, cx, cy, c):
        """Little play-control symbols, centered on (cx, cy)."""
        if kind == "next":
            for dx in (-5, 1):
                poly([(cx + dx, cy - 5), (cx + dx + 6, cy), (cx + dx, cy + 5)], fill=c)
        elif kind == "prev":
            for dx in (-1, 5):
                poly([(cx + dx, cy - 5), (cx + dx - 6, cy), (cx + dx, cy + 5)], fill=c)
        elif kind == "play":
            poly([(cx - 4, cy - 6), (cx + 6, cy), (cx - 4, cy + 6)], fill=c)
        elif kind == "pause":
            box((cx - 5, cy - 6, 3.5, 12), fill=c)
            box((cx + 1.5, cy - 6, 3.5, 12), fill=c)

    def point_in(view, event):
        """Where a mouse event landed, in design units (top-left origin, window size divided out)."""
        p = view.convertPoint_fromView_(event.locationInWindow(), None)
        s = view.bounds().size.width / W
        return (p.x / s, p.y / s)

    # ---- the window's contents -------------------------------------------------------------------------
    class PanelView(NSView):
        def isFlipped(self):                    # so (0, 0) is the top-left, like the layout numbers
            return True

        def acceptsFirstMouse_(self, event):    # a click works even though the window isn't "active"
            return True

        def updateTrackingAreas(self):
            objc.super(PanelView, self).updateTrackingAreas()
            for area in list(self.trackingAreas()):
                self.removeTrackingArea_(area)
            # 0x01 enter/exit, 0x02 moved, 0x80 even when not active, 0x200 follow the visible rect
            area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(self.bounds(), 0x01 | 0x02 | 0x80 | 0x200, self, None)
            self.addTrackingArea_(area)

        def mouseMoved_(self, event):
            hit = Layout.hit(point_in(self, event))
            name = hit[0] if hit else None
            if name != S.hover:
                S.hover = name
                self.setNeedsDisplay_(True)

        def mouseExited_(self, event):
            S.hover = None
            self.setNeedsDisplay_(True)

        def mouseDown_(self, event):
            hit = Layout.hit(point_in(self, event))
            self.start_mouse = NSEvent.mouseLocation()           # screen position (y counts upward)
            frame = controller.win.frame()
            self.start_origin = (frame.origin.x, frame.origin.y)
            self.start_size = (frame.size.width, frame.size.height)
            if not hit:
                self.mode = "move"                               # empty glass: drag to move the window
                return
            name, value = hit
            if name == "close":
                self.mode = "button"
                controller.hide()
                if CLOSE_QUITS_SPOTIFY:
                    threading.Thread(target=spotify.quit_app, daemon=True).start()
            elif name == "grip":
                self.mode = "resize"
            elif name in ("seek", "volume"):
                self.mode = "scrub"
                do(name, value)
            else:
                self.mode = "button"
                do(name, value)
            self.setNeedsDisplay_(True)

        def mouseDragged_(self, event):
            mode = getattr(self, "mode", None)
            now = NSEvent.mouseLocation()
            dx, dy = now.x - self.start_mouse.x, now.y - self.start_mouse.y
            if mode == "move":
                controller.win.setFrameOrigin_((self.start_origin[0] + dx, self.start_origin[1] + dy))
            elif mode == "resize":
                try:
                    # pull OUTWARD (right and/or down) = bigger, push INWARD (left and/or up) = smaller.
                    # (screen y counts upward, so dragging down is a negative dy)
                    controller.resize_to(clamp_width(self.start_size[0] + dx - dy * W / H), self.start_origin, self.start_size)
                except Exception as e:
                    print("panel resize error:", e)
            elif mode == "scrub":
                hit = Layout.hit(point_in(self, event))
                if hit and hit[0] in ("seek", "volume"):
                    do(hit[0], hit[1])

        def mouseUp_(self, event):
            self.mode = None

        def drawRect_(self, dirty):
            try:
                scale = self.bounds().size.width / W
                S.scale = scale
                NSGraphicsContext.saveGraphicsState()
                t = NSAffineTransform.transform()
                t.scaleBy_(scale)
                t.concat()
                poly_path(frame_points(0)).addClip()             # nothing is drawn in the cut-off corners
                draw()
                NSGraphicsContext.restoreGraphicsState()
            except Exception as e:              # a drawing slip must never kill the window
                print("panel draw error:", e)

    def draw():
        info = S.info
        state = info.get("state", "closed")
        playing_or_paused = state in ("playing", "paused")

        # --- glass: light tint over the blur, a neon wash at the top, grid, scan lines
        box((0, 0, W, H), fill=INK, fill_alpha=TINT_ALPHA)
        for i in range(0, 120, 2):
            box((0, i, W, 2), fill=BLUE, fill_alpha=0.20 * (1 - i / 120))
        for gx in range(0, W + 1, 24):
            line(gx, 0, gx, H, BLUE, 0.5, 0.08)
        for gy in range(0, H + 1, 24):
            line(0, gy, W, gy, BLUE, 0.5, 0.08)
        for sy in range(0, H, 3):
            line(0, sy, W, sy, WHITE, 0.6, 0.035)
        if SWEEP:                                                  # a bright band slides down every few seconds
            centre = (time.time() * 55) % (H + 120) - 60
            for k in range(-22, 23, 2):
                y = centre + k
                if 0 <= y <= H:
                    box((0, y, W, 2), fill=PALE, fill_alpha=0.10 * (1 - abs(k) / 23))

        # --- frame: neon outer line, thin inner line, white armor edges on two corners
        poly(frame_points(1), stroke=BLUE, width=1.8, stroke_alpha=1.0, glow=9)
        poly(frame_points(6), stroke=BLUE, width=0.8, stroke_alpha=0.5)
        c = CUT
        line(c, 1, 1, c, WHITE, 3, 0.95, glow=7)                  # top-left cut edge
        line(W - c, H - 1, W - 1, H - c, WHITE, 3, 0.95, glow=7)  # bottom-right cut edge
        for x in range(60, 200, 8):                               # tick ruler along the top
            line(x, 1, x, 4 if (x // 8) % 5 else 7, WHITE, 1, 0.55)

        # --- header
        box((20, 14, 4, 26), fill=BLUE, glow=8)
        text("501ST LEGION", 31, 12, 10, GREY, False, 3.0)
        text("MUSIC", 31, 22, 17, WHITE, True, 4.0, glow=7)
        hov = S.hover == "close"
        label = "CLOSE"
        lw = text_width(label, 12, True, 2.5)
        cx, cy, cw, ch = Layout.close
        poly(chamfer((W - 28 - lw - 14, 16, lw + 28, 20), 5), fill=BLUE if hov else None, fill_alpha=0.4,
             stroke=WHITE if hov else BLUE, width=1, stroke_alpha=1.0 if hov else 0.7, glow=5 if hov else 3)
        text(label, W - 28 - lw, 19, 12, WHITE if hov else PALE, True, 2.5)

        # --- cover with armor corner brackets
        ax, ay, aw, ah = Layout.art
        if S.art is not None and playing_or_paused:
            # respectFlipped: our view counts y from the top, so the picture must not draw upside down
            S.art.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
                NSMakeRect(ax, ay, aw, ah), NSZeroRect, 2, 1.0, True, None)
        else:
            box(Layout.art, fill=BLUE, fill_alpha=0.08)
            text("NO", ax + 37, ay + 30, 14, PALE, False, 2.0, 0.7)
            text("ART", ax + 33, ay + 48, 14, PALE, False, 2.0, 0.7)
        box(Layout.art, stroke=BLUE, width=0.8, stroke_alpha=0.6)
        for (bx, by, sx, sy) in ((ax - 3, ay - 3, 1, 1), (ax + aw + 3, ay - 3, -1, 1),
                                 (ax - 3, ay + ah + 3, 1, -1), (ax + aw + 3, ay + ah + 3, -1, -1)):
            line(bx, by, bx + 11 * sx, by, WHITE, 2, 0.95, glow=5)
            line(bx, by, bx, by + 11 * sy, WHITE, 2, 0.95, glow=5)

        # --- title / artist / state
        tx = Layout.text_x
        room = W - tx - 22
        if playing_or_paused:
            title = ellipsize(info.get("title", ""), lambda s: text_width(s, 22, True, 0.5) <= room)
            artist = ellipsize(info.get("artist", ""), lambda s: text_width(s, 16, False, 0.5) <= room)
            text(title, tx, Layout.title_y, 22, WHITE, True, 0.5, glow=6)
            text(artist, tx, Layout.artist_y, 16, PALE, False, 0.5)
            on = state == "playing"
            box((tx, Layout.state_y + 3, 7, 7), fill=GREEN if on else GREY, glow=6 if on else 0)
            text("PLAYING" if on else "PAUSED", tx + 14, Layout.state_y, 12, GREEN if on else GREY, True, 3.0)
        elif state == "stopped":
            text("NOTHING PLAYING", tx, Layout.title_y, 18, WHITE, True, 1.0)
            text("press PLAY in Spotify", tx, Layout.artist_y, 14, PALE, False, 0.5)
        elif state == "error":
            if info.get("permission"):
                text("NEEDS PERMISSION", tx, Layout.title_y, 18, WHITE, True, 1.0)
                text("Allow Terminal to control", tx, Layout.artist_y, 13, PALE, False, 0.5)
                text("Spotify (System Settings >", tx, Layout.artist_y + 15, 13, PALE, False, 0.5)
                text("Privacy > Automation)", tx, Layout.artist_y + 30, 13, PALE, False, 0.5)
            else:
                text("CAN'T REACH SPOTIFY", tx, Layout.title_y, 16, WHITE, True, 1.0)
                text("see the Terminal for why", tx, Layout.artist_y, 13, PALE, False, 0.5)
        else:
            text("SPOTIFY IS CLOSED", tx, Layout.title_y, 18, WHITE, True, 1.0)
            text("press PLAY to open it", tx, Layout.artist_y, 14, PALE, False, 0.5)

        # --- volume
        vx, vy, vw, vh = Layout.volume
        text("VOL", tx, vy - 5, 11, GREY, True, 2.0)
        segments(Layout.volume, max(0, min(100, info.get("volume", 50))) / 100.0, 20, BLUE)

        # --- progress
        px, py, pw, ph = Layout.progress
        duration = info.get("duration", 0) or 0
        frac = min(1.0, shown_position() / duration) if (duration and playing_or_paused) else 0.0
        segments(Layout.progress, frac, 48, WHITE)
        if playing_or_paused:
            text(fmt_time(shown_position()), px, py + 8, 11, GREY, False, 1.5)
            end = fmt_time(duration)
            text(end, px + pw - text_width(end, 11, False, 1.5), py + 8, 11, GREY, False, 1.5)

        # --- buttons (armor-plate shapes)
        for name, label in (("prev", "PREV"), ("play", "PAUSE" if state == "playing" else "PLAY"), ("next", "NEXT")):
            rect = getattr(Layout, name)
            hov = S.hover == name
            main = name == "play"
            hot = main or hov
            poly(chamfer(rect), fill=BLUE, fill_alpha=0.50 if hov else (0.24 if main else 0.07),
                 stroke=BLUE, width=1.5 if main else 1.0, stroke_alpha=1.0 if hot else 0.55, glow=7 if hot else 2)
            col = WHITE if hot else PALE
            w = text_width(label, 14, True, 3.0)
            total = 16 + w
            x0 = rect[0] + (rect[2] - total) / 2
            icon("pause" if (main and state == "playing") else name, x0 + 5, rect[1] + rect[3] / 2, col)
            text(label, x0 + 16, rect[1] + 8, 14, col, True, 3.0)

        # --- footer + resize grip
        text("FIVES  //  AUDIO", 20, 236, 10, GREY, False, 3.0, 0.7)
        gx, gy, gw, gh = Layout.grip
        gcol = WHITE if S.hover == "grip" else BLUE
        for k in (0, 5, 10, 15):
            line(gx + gw - 2 - k, gy + gh - 2, gx + gw - 2, gy + gh - 2 - k, gcol, 1.4, 0.95, glow=4)

    # ---- the window itself ----------------------------------------------------------------------------
    class Controller(NSObject):
        """Owns the window: show / hide / resize / timer."""

        def init(self):
            self = objc.super(Controller, self).init()
            self.visible = False
            return self

        def build(self):
            screen = NSScreen.mainScreen().visibleFrame()
            x = screen.origin.x + screen.size.width - W - MARGIN
            y = screen.origin.y + screen.size.height - H - MARGIN        # Cocoa's y counts from the bottom
            style = 0 | 128                                              # borderless + non-activating panel
            self.win = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, W, H), style, NSBackingStoreBuffered, False)
            win = self.win
            win.setFloatingPanel_(True)
            win.setLevel_(25)                                            # above normal windows (status level)
            win.setOpaque_(False)
            win.setBackgroundColor_(NSColor.clearColor())
            win.setHasShadow_(True)
            win.setHidesOnDeactivate_(False)
            win.setBecomesKeyOnlyIfNeeded_(True)
            win.setAcceptsMouseMovedEvents_(True)
            win.setReleasedWhenClosed_(False)
            win.setCollectionBehavior_(1 | 16 | 256)                     # all desktops + over full-screen apps
            self.fx = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
            fx = self.fx
            fx.setMaterial_(13)                                          # "HUD window" frosted glass
            fx.setBlendingMode_(0)                                       # blur what is BEHIND the window
            fx.setState_(1)                                              # stay frosted even when not active
            try:
                fx.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameVibrantDark"))
            except Exception:
                pass
            win.setContentView_(fx)
            self.view = PanelView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
            self.view.setAutoresizingMask_(18)                           # follows the window's size
            fx.addSubview_(self.view)
            self.apply_shape(W)

        def apply_shape(self, width):
            """Give the frosted glass the cut-corner outline (otherwise it stays a plain rectangle)."""
            try:
                scale = width / W
                size = (width, H * scale)

                def handler(rect):
                    NSColor.whiteColor().set()
                    poly_path(frame_points(0), scale).fill()
                    return True
                self.fx.setMaskImage_(NSImage.imageWithSize_flipped_drawingHandler_(size, True, handler))
                self.win.invalidateShadow()
            except Exception as e:
                print("panel: couldn't shape the glass:", e)

        def resize_to(self, width, origin, size):
            """Resize keeping the top-left corner where it is (Cocoa's origin is the bottom-left)."""
            height = width * H / W
            top = origin[1] + size[1]
            self.win.setFrame_display_(NSMakeRect(origin[0], top - height, width, height), True)
            self.apply_shape(width)

        def show(self):
            self.visible = True
            self.win.setAlphaValue_(0.0)
            self.win.orderFrontRegardless()
            self.win.animator().setAlphaValue_(1.0)
            S.refresh.set()

        def hide(self):
            self.visible = False
            self.win.orderOut_(None)

        def toggle(self):
            self.hide() if self.visible else self.show()

        def tick_(self, timer):
            if self.visible:
                self.view.setNeedsDisplay_(True)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)                    # "accessory": no Dock icon, no menu bar of its own
    controller = Controller.alloc().init()
    controller.build()
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.1, controller, "tick:", None, True)

    threading.Thread(target=poll_loop, daemon=True).start()

    if "--hidden" not in sys.argv:
        controller.show()

    def commands():
        """eyes.py talks to us through our stdin, one word per line."""
        for raw in sys.stdin:
            word = raw.strip().lower()
            if word == "toggle":
                AppHelper.callAfter(controller.toggle)
            elif word == "show":
                AppHelper.callAfter(controller.show)
            elif word == "hide":
                AppHelper.callAfter(controller.hide)
            elif word == "quit":
                break
        AppHelper.callAfter(app.terminate_, None)      # stdin closed = eyes.py is gone: quit too

    if not sys.stdin.isatty():
        threading.Thread(target=commands, daemon=True).start()
    signal.signal(signal.SIGINT, lambda *a: app.terminate_(None))     # Ctrl-C quits (checked every tick)
    app.run()


if __name__ == "__main__":
    main()
