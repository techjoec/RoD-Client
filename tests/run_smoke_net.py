import sys, time
sys.path.insert(0, '.')
from tests.mock_server import MockMudServer
from core_network import NetworkClient

srv = MockMudServer(); srv.start()
out = []

def on_text(s):
    out.append(s)

def on_disc():
    out.append('<disc>')

nc = NetworkClient(on_text, on_disc)
nc.connect('127.0.0.1', srv.port, timeout=3.0)
print('connected', srv.port, flush=True)
end = time.time() + 8
while time.time() < end and not any('Welcome' in s for s in out):
    time.sleep(0.05)
print('banner?', any('Welcome' in s for s in out), flush=True)
nc.send_line('look')
end = time.time() + 8
while time.time() < end and not any('You said: look' in s for s in out):
    time.sleep(0.05)
print('echo?', any('You said: look' in s for s in out), flush=True)
print('OUT:', ''.join(out)[0:200], flush=True)
nc.close(); srv.stop()
ok = any('Welcome' in s for s in out) and any('You said: look' in s for s in out)
print('network OK' if ok else 'network FAIL', flush=True)
sys.exit(0 if ok else 1)

