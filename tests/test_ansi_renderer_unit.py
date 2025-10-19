from ansi_renderer import color_from_ansi, xterm_color, AnsiRenderer


def test_color_from_ansi_palette_and_bounds():
    # Lower/upper bound clamping on palette indices
    assert color_from_ansi(-5) == "#000000"
    assert color_from_ansi(0) == "#000000"
    assert color_from_ansi(15) == "#ffffff"
    assert color_from_ansi(99) == "#ffffff"


def test_color_from_ansi_extended_and_xterm():
    # xterm tuple
    assert xterm_color(16) == "#000000"
    assert xterm_color(21).startswith("#")
    assert color_from_ansi(("xterm", 255)) == "#eeeeee"
    # rgb tuple clamps values
    assert color_from_ansi(("rgb", -1, 128, 300)) == "#0080ff"


class _FakeText:
    def __init__(self):
        self.buf = ""
        self.tags = {}
        self._last_line_start = 0

    def tag_configure(self, tag, **kw):
        self.tags[tag] = kw

    def insert(self, index, text, tags):
        assert index == "end"
        self.buf += text

    def index(self, spec):
        # Only used for carriage return handling; return placeholders
        return spec

    def delete(self, start, end):
        # Delete current line content
        last_nl = self.buf.rfind("\n")
        if last_nl == -1:
            self.buf = ""
        else:
            self.buf = self.buf[: last_nl + 1]


def test_ansi_renderer_write_and_cr_behavior():
    t = _FakeText()
    ar = AnsiRenderer(t)
    ar.write("Hello \x1b[31mRED\x1b[0m world\n")
    # Text appended; no carriage return replacement
    assert "Hello " in t.buf and "RED" in t.buf and "world" in t.buf
    # Carriage return should replace line start
    ar.write("Line1\nCar\rXYZ")
    assert t.buf.endswith("XYZ")

    # Extended colors and attributes should not error and should configure tags
    ar.write(" \x1b[1;4mBOLDUL\x1b[22;24m")
    ar.write(" \x1b[38;5;196mX\x1b[48;2;10;20;30mY\x1b[7mZ\x1b[27m")
    assert t.tags  # some tags configured


def test_ansi_renderer_handles_split_escape_sequences():
    t = _FakeText()
    ar = AnsiRenderer(t)
    # Split ESC sequence across writes
    ar.write("Start ")
    ar.write("\x1b[")
    ar.write("31mRED\x1b[0m End")
    # No literal '31m' should appear; text should include RED
    assert "31m" not in t.buf and "Start " in t.buf and "RED" in t.buf and t.buf.endswith(" End")
    # ESC at end of chunk should also be buffered properly
    t2 = _FakeText(); ar2 = AnsiRenderer(t2)
    ar2.write("X:\x1b")
    ar2.write("[32mG\x1b[0m")
    assert t2.buf.endswith("X:G") and "32m" not in t2.buf
