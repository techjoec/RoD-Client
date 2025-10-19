import pytest
try:
    import tkinter as tk
except Exception:
    tk = None
try:
    from ansi_renderer import AnsiRenderer
except Exception:
    AnsiRenderer = None


def test_ansi_basic():
    if tk is None or AnsiRenderer is None:
        pytest.skip("tkinter/AnsiRenderer not available")
    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("tkinter display not available")
    root.withdraw()
    t = tk.Text(root)
    t.pack()
    ar = AnsiRenderer(t)
    ar.write("Hello \x1b[31mred\x1b[0m world\rHi")
    val = t.get("1.0", "end-1c")
    # Carriage return should replace line start; final text should end with 'Hi'
    assert "red" in val and val.endswith("Hi")
    # Ensure tags created
    assert len(t.tag_names()) > 0
    root.destroy()
    print("OK: ansi basic")


if __name__ == "__main__":
    test_ansi_basic()
    print("All ansi smoke tests passed.")
