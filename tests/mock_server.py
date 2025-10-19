import socket
import threading
import time

IAC=255; SE=240; SB=250; WILL=251; WONT=252; DO=253; DONT=254
ECHO=1; SGA=3; TTYPE=24; NAWS=31


class MockMudServer:
    def __init__(self, host='127.0.0.1', port=0):
        self.host = host
        self.port = port
        self._srv = None
        self._thr = None
        self._stop = threading.Event()
        self.addr = None

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(1)
        self._srv = s
        self.port = s.getsockname()[1]
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()

    def stop(self):
        self._stop.set()
        try:
            if self._srv:
                self._srv.close()
        except Exception:
            pass
        if self._thr:
            self._thr.join(timeout=2)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._srv.settimeout(1.0)
                conn, addr = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.addr = addr
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

    def _client(self, c: socket.socket):
        c.settimeout(5.0)
        try:
            # Negotiate: DO TTYPE/NAWS; WILL SGA
            c.sendall(bytes([IAC, DO, TTYPE, IAC, DO, NAWS, IAC, WILL, SGA]))
            time.sleep(0.05)
            # Request TTYPE
            c.sendall(bytes([IAC, SB, TTYPE, 1, IAC, SE]))
            # Allow client to reply before banner
            time.sleep(0.1)
            # Send colorful banner
            banner = b"\x1b[32mWelcome\x1b[0m to MockMUD!\r\n>"
            c.sendall(banner)
            # Echo back any lines
            buf = b""
            while not self._stop.is_set():
                try:
                    d = c.recv(4096)
                    if not d:
                        break
                except socket.timeout:
                    continue
                buf += d
                # Basic CRLF line split
                while b"\r\n" in buf:
                    line, buf = buf.split(b"\r\n", 1)
                    out = b"You said: " + line + b"\r\n>"
                    c.sendall(out)
        finally:
            try:
                c.close()
            except Exception:
                pass


if __name__ == '__main__':
    srv = MockMudServer()
    srv.start()
    print(f"listening on {srv.host}:{srv.port}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    srv.stop()
