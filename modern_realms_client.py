import json
import os
import queue
import threading
import tkinter.font as tkfont
from tkinter import filedialog
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox

# Import the shared NetworkClient implementation that wraps Python's
# telnetlib.  This replaces the bespoke Telnet negotiation logic in
# this module so that all Telnet handling occurs in one maintained
# location (core_network.py).  We alias the import as CoreNetworkClient
# to avoid name collisions with the local NetworkClient class defined
# below; the UI uses CoreNetworkClient instead of the local version.
from core_network import NetworkClient as CoreNetworkClient
from ansi_renderer import AnsiRenderer




DEFAULT_MACROS = [
    {"label": "Look", "text": "look"},
    {"label": "Score", "text": "score"},
    {"label": "Inv", "text": "inventory"},
    {"label": "Who", "text": "/who"},
    {"label": "Say", "text": "say Hello!"},
    {"label": "Tell", "text": "tell friend hi"},
    {"label": "Cast", "text": "cast 'light'"},
    {"label": "Flee", "text": "flee"},
    {"label": "Group", "text": "group"},
    {"label": "Help", "text": "help"},
]


class ModernClientUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Modern Realms Client")
        self.geometry("900x600")
        self.minsize(700, 400)

        # State
        self.connected = False
        self.echo_var = tk.BooleanVar(value=False)
        self.host_var = tk.StringVar(value="realmsofdespair.com")
        self.port_var = tk.StringVar(value="4000")
        self.status_var = tk.StringVar(value="Disconnected")
        self.msg_queue = queue.Queue()
        self.client = None
        self.macros = self.load_macros()

        self._build_widgets()
        self._build_menus()
        self.after(15, self._drain_queue)
        self._naws_debounce_id = None
        self._last_naws_sent = None  # (cols, rows)
        self._last_geom = None  # (width, height)

    def load_macros(self):
        path = os.path.join(os.getcwd(), "macros.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    buttons = data.get("buttons")
                    if isinstance(buttons, list) and buttons:
                        # normalize entries
                        out = []
                        for b in buttons[:10]:
                            if isinstance(b, dict):
                                out.append({
                                    "label": str(b.get("label", "Macro")),
                                    "text": str(b.get("text", "")),
                                })
                        # pad to 10
                        while len(out) < 10:
                            out.append({"label": "Macro", "text": ""})
                        return out
            except Exception:
                pass
        # default
        return [m.copy() for m in DEFAULT_MACROS]

    def save_macros(self):
        path = os.path.join(os.getcwd(), "macros.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"buttons": self.macros}, f, indent=2)
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save macros: {e}")

    def _build_widgets(self):
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text="Host:").pack(side=tk.LEFT)
        host_entry = ttk.Entry(top, textvariable=self.host_var, width=28)
        host_entry.pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(top, text="Port:").pack(side=tk.LEFT)
        port_entry = ttk.Entry(top, textvariable=self.port_var, width=6)
        port_entry.pack(side=tk.LEFT, padx=(4, 10))

        self.connect_btn = ttk.Button(top, text="Connect", command=self.on_connect)
        self.connect_btn.pack(side=tk.LEFT)
        self.disconnect_btn = ttk.Button(top, text="Disconnect", command=self.on_disconnect, state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.LEFT, padx=(6, 0))

        ttk.Checkbutton(top, text="Echo", variable=self.echo_var, command=self._update_echo_led).pack(side=tk.LEFT, padx=(16, 8))

        # LEDs: echo, tx, rx
        leds = ttk.Frame(top)
        leds.pack(side=tk.LEFT, padx=(4, 0))
        self.echo_led = self._create_led(leds, tooltip="Echo")
        self.tx_led = self._create_led(leds, tooltip="TX")
        self.rx_led = self._create_led(leds, tooltip="RX")
        self._tx_timer = None
        self._rx_timer = None

        status = ttk.Label(top, textvariable=self.status_var, anchor=tk.E)
        status.pack(side=tk.RIGHT)

        mid = ttk.Frame(self)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        # Left: text output with ANSI rendering
        left = ttk.Frame(mid)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text = tk.Text(left, wrap=tk.WORD, state=tk.DISABLED, background="#111", foreground="#ddd", takefocus=0)
        self.ansi = AnsiRenderer(self.text)
        yscroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=yscroll.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Context menu for text
        self._text_menu = tk.Menu(self, tearoff=0)
        self._text_menu.add_command(label="Copy", command=self._copy_selection)
        self._text_menu.add_command(label="Select All", command=self._select_all)
        self._text_menu.add_separator()
        self._text_menu.add_command(label="Clear", command=self._clear_output)
        self.text.bind("<Button-3>", self._show_text_menu)
        self.text.bind("<Double-Button-1>", self._backscroll_double_click)

        # Right: controls (directions + macros)
        right = ttk.Frame(mid)
        right.pack(side=tk.RIGHT, fill=tk.Y)

        dir_frame = ttk.LabelFrame(right, text="Directions")
        dir_frame.pack(side=tk.TOP, padx=4, pady=4)
        self._build_dirpad(dir_frame)

        macro_frame = ttk.LabelFrame(right, text="Macros")
        macro_frame.pack(side=tk.TOP, padx=4, pady=8, fill=tk.X)
        self.macro_buttons = []
        for i in range(10):
            btn = ttk.Button(macro_frame, text=self.macros[i]["label"], width=12)
            btn.grid(row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")
            btn.bind("<Button-1>", lambda e, idx=i: self._macro_send(idx))
            btn.bind("<Button-3>", lambda e, idx=i: self._macro_edit(idx))
            self.macro_buttons.append(btn)

        bottom = ttk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=6)
        self.input_var = tk.StringVar()
        input_entry = ttk.Entry(bottom, textvariable=self.input_var)
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        input_entry.bind("<Return>", self._on_send_enter)
        ttk.Button(bottom, text="Send", command=self.on_send).pack(side=tk.LEFT, padx=(6, 0))
        # Send NAWS updates on resize (debounced)
        self.bind("<Configure>", self._on_resize)
        # Keep a reference and focus input by default
        self.input_entry = input_entry
        try:
            self.input_entry.focus_set()
        except Exception:
            pass
        # Ensure focus after initial layout settles
        self.after(100, lambda: self.input_entry.focus_set())
        # Also schedule after idle to override any late focus steals
        try:
            self.after_idle(lambda: self.input_entry.focus_force())
        except Exception:
            pass

    def _build_menus(self):
        menubar = tk.Menu(self)
        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="Connect", command=self.on_connect)
        filem.add_command(label="Disconnect", command=self.on_disconnect)
        filem.add_separator()
        filem.add_command(label="Save Log…", command=self._save_log)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filem)

        editm = tk.Menu(menubar, tearoff=0)
        editm.add_command(label="Copy", command=self._copy_selection)
        editm.add_command(label="Select All", command=self._select_all)
        editm.add_command(label="Clear Output", command=self._clear_output)
        menubar.add_cascade(label="Edit", menu=editm)

        optm = tk.Menu(menubar, tearoff=0)
        optm.add_checkbutton(label="Echo", variable=self.echo_var, command=self._update_echo_led)
        optm.add_command(label="Font…", command=self._choose_font)
        menubar.add_cascade(label="Options", menu=optm)

        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=helpm)

        self.config(menu=menubar)

    def _build_dirpad(self, parent):
        # Layout:
        #   NW  N  NE
        #   W   .   E
        #   SW  S  SE
        #   U   .   D
        directions = {
            (0, 0): ("NW", "nw"), (0, 1): ("N", "n"), (0, 2): ("NE", "ne"),
            (1, 0): ("W", "w"), (1, 2): ("E", "e"),
            (2, 0): ("SW", "sw"), (2, 1): ("S", "s"), (2, 2): ("SE", "se"),
            (3, 0): ("U", "u"), (3, 2): ("D", "d"),
        }
        self._dir_repeat_jobs = {}
        for (r, c), (label, cmd) in directions.items():
            btn = ttk.Button(parent, text=label, width=4)
            btn.grid(row=r, column=c, padx=2, pady=2)
            btn.bind("<ButtonPress-1>", lambda e, t=cmd, b=btn: self._start_dir_repeat(t, b))
            btn.bind("<ButtonRelease-1>", lambda e, t=cmd, b=btn: self._stop_dir_repeat(b))
            btn.bind("<Leave>", lambda e, b=btn: self._stop_dir_repeat(b))

    def _start_dir_repeat(self, cmd: str, btn):
        self._send_text(cmd)
        def repeat():
            self._send_text(cmd)
            self._dir_repeat_jobs[btn] = self.after(200, repeat)
        # initial delay for press-and-hold feel
        self._dir_repeat_jobs[btn] = self.after(400, repeat)

    def _stop_dir_repeat(self, btn):
        job = self._dir_repeat_jobs.pop(btn, None)
        if job:
            self.after_cancel(job)

    def _macro_send(self, idx: int):
        text = self.macros[idx]["text"].strip()
        if text:
            self._send_text(text)

    def _macro_edit(self, idx: int):
        current = self.macros[idx]
        label = simpledialog.askstring("Edit Macro", "Button label:", initialvalue=current["label"], parent=self)
        if label is None:
            return
        text = simpledialog.askstring("Edit Macro", "Command text:", initialvalue=current["text"], parent=self)
        if text is None:
            return
        self.macros[idx] = {"label": label, "text": text}
        self.macro_buttons[idx].configure(text=label)
        self.save_macros()

    def _append_text(self, s: str):
        self.text.configure(state=tk.NORMAL)
        self.ansi.write(s)
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def _drain_queue(self):
        # Batch multiple queued messages into a single write to minimize
        # state flips and tagging overhead in the Text widget.
        items = []
        try:
            while True:
                items.append(self.msg_queue.get_nowait())
        except queue.Empty:
            pass
        if items:
            self.text.configure(state=tk.NORMAL)
            self.ansi.write("".join(items))
            self.text.see(tk.END)
            self.text.configure(state=tk.DISABLED)
        # Faster tick for responsiveness
        self.after(10, self._drain_queue)

    def on_connect(self):
        if self.connected:
            return
        host = self.host_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid Port", "Port must be a number")
            return
        if not host:
            messagebox.showerror("Invalid Host", "Please enter a hostname")
            return
        self.status_var.set(f"Connecting to {host}:{port}…")
        self.connect_btn.configure(state=tk.DISABLED)
        self.update_idletasks()

        def do_connect():
            try:
                # Use the shared NetworkClient from core_network rather than the
                # local implementation.  This ensures all Telnet handling is
                # delegated to a maintained module rather than duplicating
                # protocol code here.
                self.client = CoreNetworkClient(self._on_text_from_net, self._on_disconnected)
                self.client.connect(host, port, timeout=10.0)
            except Exception as e:
                self.after(0, lambda: self._on_connect_failed(str(e)))
                return
            self.after(0, self._on_connected)

        threading.Thread(target=do_connect, daemon=True).start()

    def _on_connect_failed(self, err: str):
        self.client = None
        self.status_var.set(f"Connect failed: {err}")
        self.connect_btn.configure(state=tk.NORMAL)

    def _on_connected(self):
        self.connected = True
        self.status_var.set("Connected")
        self.connect_btn.configure(state=tk.DISABLED)
        self.disconnect_btn.configure(state=tk.NORMAL)
        try:
            self.input_entry.focus_set()
        except Exception:
            pass

    def _on_disconnected(self):
        self.connected = False
        self.after(0, lambda: self.status_var.set("Disconnected"))
        self.after(0, lambda: self.disconnect_btn.configure(state=tk.DISABLED))
        self.after(0, lambda: self.connect_btn.configure(state=tk.NORMAL))
        try:
            self.input_entry.focus_set()
        except Exception:
            pass

    def on_disconnect(self):
        if self.client:
            self.client.close()
            self.client = None

    def _on_text_from_net(self, s: str):
        # Normalize newlines
        # Keep \r for prompt updates; renderer will handle it
        self.msg_queue.put(s)
        self._pulse_rx_led()

    def _send_text(self, line: str):
        if self.echo_var.get():
            self.msg_queue.put(line + "\n")
        if self.client and self.connected:
            self.client.send_line(line)
            self._pulse_tx_led()

    def on_send(self):
        # Send exactly what the user typed, including blanks
        line = self.input_var.get()
        self._send_text(line)
        self.input_var.set("")
        try:
            self.input_entry.focus_set()
        except Exception:
            pass

    def _on_send_enter(self, event):
        self.on_send()
        return "break"

    def _on_resize(self, event):
        # Debounce NAWS; only send if size changed and NAWS enabled
        # Only send NAWS if the client exists and NAWS is active
        if not (self.client and getattr(self.client, "naws_enabled", lambda: False)()):
            return
        try:
            w, h = self.text.winfo_width(), self.text.winfo_height()
        except Exception:
            return
        if self._last_geom == (w, h):
            return
        self._last_geom = (w, h)

        def send_naws_once():
            try:
                cols = max(20, min(255, int(self.text.winfo_width() / 8)))
                rows = max(5, min(255, int(self.text.winfo_height() / 16)))
            except Exception:
                cols, rows = 120, 40
            if self._last_naws_sent != (cols, rows):
                self._last_naws_sent = (cols, rows)
                self.client.send_naws(cols, rows)
            self._naws_debounce_id = None

        if self._naws_debounce_id is not None:
            self.after_cancel(self._naws_debounce_id)
        self._naws_debounce_id = self.after(200, send_naws_once)

    # UI helpers and parity features
    def _create_led(self, parent, tooltip=""):
        c = tk.Canvas(parent, width=12, height=12, highlightthickness=0, bg=self.cget("background"))
        c.pack(side=tk.LEFT, padx=2)
        c._oval = c.create_oval(2, 2, 10, 10, fill="#444", outline="#222")
        return c

    def _set_led(self, led_canvas, on: bool, color="#2ecc71"):
        c = led_canvas
        c.itemconfigure(c._oval, fill=(color if on else "#444"))

    def _update_echo_led(self):
        self._set_led(self.echo_led, self.echo_var.get(), color="#f1c40f")

    def _pulse_tx_led(self):
        self._set_led(self.tx_led, True, color="#e74c3c")
        if self._tx_timer:
            self.after_cancel(self._tx_timer)
        self._tx_timer = self.after(120, lambda: self._set_led(self.tx_led, False))

    def _pulse_rx_led(self):
        self._set_led(self.rx_led, True, color="#2ecc71")
        if self._rx_timer:
            self.after_cancel(self._rx_timer)
        self._rx_timer = self.after(120, lambda: self._set_led(self.rx_led, False))

    def _show_text_menu(self, event):
        try:
            self._text_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._text_menu.grab_release()

    def _copy_selection(self):
        try:
            sel = self.text.selection_get()
        except Exception:
            sel = ""
        if sel:
            self.clipboard_clear()
            self.clipboard_append(sel)

    def _select_all(self):
        self.text.tag_add("sel", "1.0", "end")

    def _clear_output(self):
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", "end")
        self.text.configure(state=tk.DISABLED)

    def _backscroll_double_click(self, event):
        # Copy clicked line into input (parity with BackScrollDblClick intent)
        index = self.text.index(f"@{event.x},{event.y}")
        line_start = self.text.index(f"{index} linestart")
        line_end = self.text.index(f"{index} lineend")
        line = self.text.get(line_start, line_end).strip()
        if line:
            self.input_var.set(line)

    def _save_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files","*.txt"),("All Files","*.*")])
        if not path:
            return
        try:
            data = self.text.get("1.0", "end-1c")
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save log: {e}")

    def _choose_font(self):
        try:
            current = tkfont.Font(font=self.text["font"]) if "font" in self.text.keys() else tkfont.nametofont("TkFixedFont")
            fam = simpledialog.askstring("Font", "Font family (e.g., 'Courier New'):", initialvalue=current.actual().get("family", "Courier New"), parent=self)
            if fam is None:
                return
            size_str = simpledialog.askstring("Font", "Size (e.g., 10):", initialvalue=str(current.actual().get("size", 10)), parent=self)
            if size_str is None:
                return
            size = int(size_str)
            new_font = tkfont.Font(family=fam, size=size)
            self.text.configure(font=new_font)
        except Exception as e:
            messagebox.showerror("Font Error", str(e))

    def _show_about(self):
        messagebox.showinfo("About", "Modern Realms Client\nA modern replacement for realms.exe\nANSI + rich telnet for Realms of Despair")





def main():
    app = ModernClientUI()
    app.mainloop()


if __name__ == "__main__":
    main()
