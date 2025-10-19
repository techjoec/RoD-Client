"""Network layer for the MUD client.

This implementation wraps Python's standard :mod:`telnetlib` to manage
Telnet connections instead of using a bespoke Telnet negotiator. The goal
is to delegate the low-level Telnet protocol details to a maintained
library rather than re-implementing option negotiation and IAC handling
ourselves. Only minimal negotiation callbacks are provided here to
determine which Telnet options to accept or refuse. NAWS (window size)
support is handled by sending a sub-negotiation when the server requests
it. MCCP2 compression and other advanced MUD protocols are not supported to
keep this layer simple and robust.
"""

import os
import threading
import telnetlib
import time

from typing import Callable, Optional


class NetworkClient:
    """Basic Telnet network client using :mod:`telnetlib`.

    Parameters
    ----------
    on_text_callback : Callable[[str], None]
        Function invoked with decoded text received from the server.
    on_disconnect_callback : Callable[[], None]
        Function called when the connection is closed by either side.
    """


    # Telnet command and option codes (as integers) used for negotiation.
    IAC = 255
    DONT = 254
    DO = 253
    WONT = 252
    WILL = 251
    SB = 250
    SE = 240
    # Telnet options
    ECHO = 1
    SGA = 3
    TTYPE = 24
    NAWS = 31
    LINEMODE = 34
    NEW_ENVIRON = 39
    MSDP = 69
    MSSP = 70
    COMPRESS2 = 86
    MXP = 91
    GMCP = 201

    def __init__(self, on_text_callback: Callable[[str], None], on_disconnect_callback: Callable[[], None]):
        """Initialize the network client.

        Parameters
        ----------
        on_text_callback : callable
            Function invoked with decoded text received from the server.
        on_disconnect_callback : callable
            Function called when the connection is closed by either side.
        """
        # callbacks provided by the caller
        self.on_text = on_text_callback
        self.on_disconnect = on_disconnect_callback

        # telnet instance created on connect()
        self._tn: Optional[telnetlib.Telnet] = None

        # thread for reading incoming data
        self._rx_thread: Optional[threading.Thread] = None

        # event to signal termination
        self._stop_event = threading.Event()

        # lock protecting writes to the underlying socket
        self._send_lock = threading.Lock()

        # track whether NAWS has been negotiated so we can send updates
        self._naws_enabled = False

        # Compression is not supported in this client

    def connect(self, host: str, port: int, timeout: float = 10.0) -> None:
        """Connect to a remote host using Telnet.

        Parameters
        ----------
        host : str
            Hostname or IP address of the MUD server.
        port : int
            Port number of the MUD server.
        timeout : float, optional
            Maximum number of seconds to wait for initial connection.
        """
        if self._tn:
            raise RuntimeError("Already connected")
        # Establish a Telnet connection; this will raise on failure
        tn = telnetlib.Telnet()
        # register negotiation callback
        tn.set_option_negotiation_callback(self._on_option)
        tn.open(host, port, timeout=timeout)

        # set a short timeout on the underlying socket for non‑blocking reads
        if tn.sock is not None:
            tn.sock.settimeout(0.5)

        self._tn = tn
        self._stop_event.clear()
        self._rx_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._rx_thread.start()

    def _reader_loop(self) -> None:
        """Background thread that continuously reads from the Telnet connection.

        This loop reads available data using the ``read_eager()`` method of
        :class:`telnetlib.Telnet`.  Incoming bytes are decoded to text and
        forwarded to the application via the ``on_text`` callback.  The loop
        exits when the stop event is set or the remote host disconnects.
        """
        dbg = os.getenv('CORE_NET_LOG')
        rawpass = os.getenv('CORE_NET_RAW_PASS') == '1'

        def dlog(*args: object) -> None:
            """Write debugging information either to stdout or a log file.

            The environment variable ``CORE_NET_LOG`` controls logging: if set
            to ``'stdout'`` then messages are printed; if set to any other
            non‑empty string, it is interpreted as a file path to append log
            messages to.  Logging is silent by default.
            """
            if not dbg:
                return
            try:
                if dbg == 'stdout':
                    print('[core_net]', *args, flush=True)
                else:
                    with open(dbg, 'a', encoding='utf-8') as f:
                        f.write(' '.join(map(str, args)) + '\n')
            except Exception:
                # Don't let logging failures interfere with client operation
                pass

        try:
            while not self._stop_event.is_set():
                try:
                    # Attempt to read any available data without blocking
                    if not self._tn:
                        break
                    raw: bytes = self._tn.read_eager()
                    if raw:
                        if dbg:
                            dlog('recv', len(raw), raw[:64])
                        # No compression: process raw bytes
                        data = raw
                        # In rawpass mode simply strip out IAC sequences
                        if rawpass:
                            text_bytes = self._strip_iac(data)
                        else:
                            text_bytes = data
                        if text_bytes:
                            try:
                                decoded = text_bytes.decode('utf-8', errors='ignore')
                            except Exception:
                                decoded = text_bytes.decode('latin-1', errors='ignore')
                            if dbg:
                                dlog('emit text', len(decoded))
                            try:
                                self.on_text(decoded)
                            except Exception:
                                pass
                    else:
                        # No data available; sleep briefly
                        time.sleep(0.05)
                        continue
                except EOFError:
                    # Remote end closed connection
                    break
                except OSError:
                    break
                except Exception as e:
                    # Log unexpected errors and continue loop
                    if dbg:
                        dlog('exception', repr(e))
                    break
        finally:
            # ensure the connection is closed and callback is invoked
            self.close()
            try:
                self.on_disconnect()
            except Exception:
                pass

    def send_line(self, line: str) -> None:
        """Send a line of text to the server followed by CRLF."""
        tn = self._tn
        if not tn:
            return
        data = (line + '\r\n').encode('utf-8', errors='ignore')
        with self._send_lock:
            try:
                tn.write(data)
            except Exception:
                pass

    def close(self) -> None:
        """Close the connection and signal the reader thread to exit."""
        self._stop_event.set()
        tn = self._tn
        if tn is not None:
            try:
                tn.close()
            except Exception:
                pass
            self._tn = None

    def _get_naws_size(self) -> tuple[int, int]:
        """Return the default terminal size (cols, rows)."""
        return (120, 40)

    def send_naws(self, cols: int, rows: int) -> None:
        """Send a NAWS (Negotiate About Window Size) subnegotiation packet.

        Parameters
        ----------
        cols : int
            Number of columns in the client window.
        rows : int
            Number of rows in the client window.
        """
        tn = self._tn
        if not tn or tn.sock is None:
            return
        # Clamp values to Telnet's one‑byte range
        c = max(20, min(255, int(cols)))
        r = max(5, min(255, int(rows)))
        payload = bytes([
            self.IAC, self.SB, self.NAWS,
            0, c, 0, r,
            self.IAC, self.SE,
        ])
        with self._send_lock:
            try:
                tn.sock.sendall(payload)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Telnet negotiation callback
    # ------------------------------------------------------------------
    def _on_option(self, telnet: telnetlib.Telnet, cmd: int, opt: int) -> None:
        """Handle Telnet option negotiation.

        This callback is registered with :meth:`telnetlib.Telnet.set_option_negotiation_callback`.
        It receives the Telnet command (DO, DONT, WILL, WONT) and the option
        code.  Based on the option and our policy we respond appropriately to
        either accept or refuse the negotiation.  Currently MCCP2, MXP and
        LINEMODE are refused.
        """
        # Acquire the send lock to avoid interleaving negotiation responses
        with self._send_lock:
            # Normalize command and option to integers if they are bytes
            try:
                cmd_val = cmd if isinstance(cmd, int) else cmd[0]
                opt_val = opt if isinstance(opt, int) else opt[0]
            except Exception:
                return
            try:
                if cmd_val == self.DO:
                    # The server asks us to perform an option
                    if opt_val in (self.TTYPE, self.NAWS, self.NEW_ENVIRON, self.MSSP, self.MSDP, self.GMCP):
                        # Accept these options: send WILL
                        packet = bytes([self.IAC, self.WILL, opt_val])
                        telnet.sock.sendall(packet)
                        # If NAWS, immediately send current window size
                        if opt_val == self.NAWS:
                            self._naws_enabled = True
                            cols, rows = self._get_naws_size()
                            self.send_naws(cols, rows)
                        # If TTYPE, send terminal type (ANSI)
                        if opt_val == self.TTYPE:
                            # Send SB TTYPE IS "ANSI"
                            ttype = b"ANSI"
                            sb_packet = bytes([
                                self.IAC, self.SB, self.TTYPE, 0
                            ]) + ttype + bytes([
                                self.IAC, self.SE
                            ])
                            telnet.sock.sendall(sb_packet)
                    elif opt_val in (self.ECHO, self.SGA):
                        # Accept SGA (send WILL), refuse ECHO
                        if opt_val == self.SGA:
                            telnet.sock.sendall(bytes([self.IAC, self.WILL, opt_val]))
                        else:
                            telnet.sock.sendall(bytes([self.IAC, self.WONT, opt_val]))
                    else:
                        # Unknown or unsupported option: refuse
                        telnet.sock.sendall(bytes([self.IAC, self.WONT, opt_val]))
                elif cmd_val == self.WILL:
                    # The server will perform an option; we decide if we want it
                    if opt_val in (self.ECHO, self.SGA, self.MSSP, self.MSDP, self.GMCP):
                        telnet.sock.sendall(bytes([self.IAC, self.DO, opt_val]))
                    elif opt_val == self.COMPRESS2:
                        # MCCP2 compression is not supported; refuse
                        telnet.sock.sendall(bytes([self.IAC, self.DONT, opt_val]))
                    elif opt_val in (self.MXP, self.LINEMODE):
                        # Refuse MXP or line mode
                        telnet.sock.sendall(bytes([self.IAC, self.DONT, opt_val]))
                    else:
                        # Default: refuse unknown options
                        telnet.sock.sendall(bytes([self.IAC, self.DONT, opt_val]))
                elif cmd_val == self.DONT:
                    # Server refuses our WILL; acknowledge with WONT
                    telnet.sock.sendall(bytes([self.IAC, self.WONT, opt_val]))
                elif cmd_val == self.WONT:
                    # Server refuses our DO; acknowledge with DONT
                    telnet.sock.sendall(bytes([self.IAC, self.DONT, opt_val]))
            except Exception:
                # Ignore negotiation send errors
                pass

    # ------------------------------------------------------------------
    # Helper for rawpass logging
    # ------------------------------------------------------------------
    def _strip_iac(self, buf: bytes) -> bytes:
        """Remove Telnet IAC commands from the buffer.

        This helper is used when ``CORE_NET_RAW_PASS`` is enabled.  It
        iterates through the incoming byte stream and strips out all Telnet
        command sequences, returning only the printable text.  It does not
        attempt to interpret subnegotiations.
        """
        out = bytearray()
        i = 0
        n = len(buf)
        while i < n:
            b = buf[i]
            if b == self.IAC:
                i += 1
                if i >= n:
                    break
                cmd = buf[i]
                i += 1
                if cmd in (self.DO, self.DONT, self.WILL, self.WONT):
                    i += 1  # skip option byte
                elif cmd == self.SB:
                    # skip subnegotiation until IAC SE
                    while i < n - 1:
                        if buf[i] == self.IAC and buf[i+1] == self.SE:
                            i += 2
                            break
                        i += 1
                else:
                    # single-byte command, ignore
                    pass
            else:
                out.append(b)
                i += 1
        return bytes(out)

    # ------------------------------------------------------------------
    # Public query helpers
    # ------------------------------------------------------------------
    def naws_enabled(self) -> bool:
        """Return True if NAWS negotiation is active."""
        return self._naws_enabled
