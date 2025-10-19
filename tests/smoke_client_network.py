import threading
import time
from core_network import NetworkClient
from tests.mock_server import MockMudServer


def test_connect_and_io():
    srv = MockMudServer()
    srv.start()
    out = []
    disc = []

    def on_text(s: str):
        out.append(s)

    def on_disc():
        disc.append(True)

    nc = NetworkClient(on_text, on_disc)
    nc.connect('127.0.0.1', srv.port, timeout=3.0)
    # wait for banner
    deadline = time.time() + 2.0
    while time.time() < deadline and not any('Welcome' in s for s in out):
        time.sleep(0.05)
    nc.send_line('look')
    deadline = time.time() + 2.0
    while time.time() < deadline and not any('You said: look' in s for s in out):
        time.sleep(0.05)
    nc.close()
    time.sleep(0.2)
    srv.stop()

    buf = "".join(out)
    assert 'Welcome' in buf and 'You said: look' in buf
    print('OK: network client basic IO')


if __name__ == '__main__':
    test_connect_and_io()
    print('All network smoke tests passed.')
