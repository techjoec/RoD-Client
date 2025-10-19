import tkinter as tk


class AnsiRenderer:
    def __init__(self, text_widget: tk.Text):
        self.t = text_widget
        self.reset()
        self._tag_cache = {}
        self._carriage_return = False
        # Buffer for partial/incomplete escape sequences across writes
        self._pending_esc = ""

    def reset(self):
        self.fg = None
        self.bg = None
        self.bold = False
        self.underline = False
        self.inverse = False

    def _get_colors(self, fg, bg, bold, inverse):
        default_fg = "#dddddd"
        default_bg = "#111111"
        fg_color = default_fg if fg is None else color_from_ansi(fg, bold)
        bg_color = default_bg if bg is None else color_from_ansi(bg, False)
        if inverse:
            fg_color, bg_color = bg_color, fg_color
        return fg_color, bg_color

    def _ensure_tag(self):
        key = (self.fg, self.bg, self.bold, self.underline, self.inverse)
        if key in self._tag_cache:
            return self._tag_cache[key]
        tag = f"ansi_{key}"
        fg_color, bg_color = self._get_colors(self.fg, self.bg, self.bold, self.inverse)
        self.t.tag_configure(tag, foreground=fg_color, background=bg_color, underline=1 if self.underline else 0)
        self._tag_cache[key] = tag
        return tag

    def write(self, s: str):
        # Prepend any pending partial ESC sequence from previous call
        if self._pending_esc:
            s = self._pending_esc + s
            self._pending_esc = ""
        i = 0
        n = len(s)
        buf = []
        while i < n:
            ch = s[i]
            if ch == "\x1b":
                # If ESC is last char, defer to next write
                if i + 1 >= n:
                    self._pending_esc = s[i:]
                    break
                if s[i + 1] == "[":
                    if buf:
                        self._insert("".join(buf))
                        buf = []
                    start_esc = i
                    i += 2
                    params = []
                    num = ""
                    mode = None
                    while i < n:
                        c = s[i]
                        if c.isdigit():
                            num += c
                        elif c == ";":
                            params.append(int(num) if num else None)
                            num = ""
                        else:
                            if num or params:
                                params.append(int(num) if num else None)
                            mode = c
                            i += 1
                            break
                        i += 1
                    # Incomplete CSI (no mode char): buffer and exit
                    if mode is None:
                        self._pending_esc = s[start_esc:]
                        break
                    if mode == "m":
                        self._apply_sgr(params)
                    # Unsupported CSI modes are ignored
                    continue
                else:
                    # Not a CSI sequence; treat ESC literally
                    buf.append(ch)
                    i += 1
                    continue
            elif ch == "\r":
                if buf:
                    self._insert("".join(buf))
                    buf = []
                self._carriage_return = True
            else:
                buf.append(ch)
            i += 1
        if buf:
            self._insert("".join(buf))

    def _insert(self, text: str):
        if self._carriage_return:
            line_start = self.t.index("end-1c linestart")
            line_end = self.t.index("end-1c lineend")
            self.t.delete(line_start, line_end)
            self._carriage_return = False
        tag = self._ensure_tag()
        self.t.insert("end", text, (tag,))

    def _apply_sgr(self, params):
        if not params:
            params = [0]
        i = 0
        while i < len(params):
            p = params[i] if params[i] is not None else 0
            if p == 0:
                self.reset()
            elif p == 1:
                self.bold = True
            elif p == 4:
                self.underline = True
            elif p == 7:
                self.inverse = True
            elif p == 22:
                self.bold = False
            elif p == 24:
                self.underline = False
            elif p == 27:
                self.inverse = False
            elif p == 39:
                self.fg = None
            elif p == 49:
                self.bg = None
            elif 30 <= p <= 37:
                self.fg = p - 30
            elif 90 <= p <= 97:
                self.fg = (p - 90) + 8
            elif 40 <= p <= 47:
                self.bg = p - 40
            elif 100 <= p <= 107:
                self.bg = (p - 100) + 8
            elif p == 38 or p == 48:
                is_fg = (p == 38)
                if i + 1 < len(params) and params[i + 1] == 5 and i + 2 < len(params):
                    val = params[i + 2]
                    if val is not None:
                        if is_fg:
                            self.fg = ("xterm", int(val))
                        else:
                            self.bg = ("xterm", int(val))
                    i += 2
                elif i + 1 < len(params) and params[i + 1] == 2 and i + 4 < len(params):
                    r, g, b = params[i + 2], params[i + 3], params[i + 4]
                    if None not in (r, g, b):
                        if is_fg:
                            self.fg = ("rgb", int(r), int(g), int(b))
                        else:
                            self.bg = ("rgb", int(r), int(g), int(b))
                    i += 4
            i += 1


def color_from_ansi(code, bold=False) -> str:
    if isinstance(code, tuple):
        kind = code[0]
        if kind == "xterm":
            n = max(0, min(255, int(code[1])))
            return xterm_color(n)
        if kind == "rgb":
            r, g, b = [max(0, min(255, int(v))) for v in code[1:4]]
            return f"#{r:02x}{g:02x}{b:02x}"
    palette = [
        "#000000", "#aa0000", "#00aa00", "#aa5500",
        "#0000aa", "#aa00aa", "#00aaaa", "#aaaaaa",
        "#555555", "#ff5555", "#55ff55", "#ffff55",
        "#5555ff", "#ff55ff", "#55ffff", "#ffffff",
    ]
    idx = max(0, min(15, int(code)))
    return palette[idx]


def xterm_color(n: int) -> str:
    if 0 <= n <= 15:
        return color_from_ansi(n)
    if 16 <= n <= 231:
        n -= 16
        r = (n // 36) % 6
        g = (n // 6) % 6
        b = n % 6
        def comp(v):
            return 55 + v * 40 if v > 0 else 0
        return f"#{comp(r):02x}{comp(g):02x}{comp(b):02x}"
    if 232 <= n <= 255:
        v = 8 + (n - 232) * 10
        return f"#{v:02x}{v:02x}{v:02x}"
    return "#ffffff"
