from core_network import NetworkClient


class _Sock:
    def __init__(self):
        self.sent = bytearray()

    def sendall(self, data: bytes):
        self.sent += data


class _DummyTelnet:
    def __init__(self):
        self.sock = _Sock()


def test_strip_iac_and_send_naws_clamping():
    out_log = []
    nc = NetworkClient(lambda s: out_log.append(s), lambda: None)
    # IAC DO 1; plain text ABC; IAC SB ... IAC SE; printable XYZ
    IAC=255; DO=253; SE=240; SB=250
    buf = bytes([IAC, DO, 1]) + b"ABC" + bytes([IAC, SB, 24, 1, IAC, SE]) + b"XYZ"
    stripped = nc._strip_iac(buf)
    assert stripped == b"ABCXYZ"

    # NAWS send uses one-byte size; ensure clamping from (10, 1000) -> (20, 255)
    dummy = _DummyTelnet()
    nc._tn = dummy  # patch in dummy telnet
    nc.send_naws(10, 1000)
    sent = bytes(dummy.sock.sent)
    assert sent.endswith(bytes([IAC, SB, nc.NAWS, 0, 20, 0, 255, IAC, nc.SE]))


def test_option_negotiation_paths():
    nc = NetworkClient(lambda s: None, lambda: None)
    tn = _DummyTelnet()
    # Exercise DO TTYPE, NAWS and NEW_ENVIRON acceptance
    nc._on_option(tn, nc.DO, nc.TTYPE)
    nc._on_option(tn, nc.DO, nc.NAWS)
    nc._on_option(tn, nc.DO, nc.NEW_ENVIRON)
    # Exercise DO ECHO refused, DO SGA accepted
    nc._on_option(tn, nc.DO, nc.ECHO)
    nc._on_option(tn, nc.DO, nc.SGA)
    # Exercise WILL ECHO/SGA accepted, WILL COMPRESS2 refused by default, WILL LINEMODE refused
    nc._on_option(tn, nc.WILL, nc.ECHO)
    nc._on_option(tn, nc.WILL, nc.SGA)
    nc._on_option(tn, nc.WILL, nc.COMPRESS2)
    nc._on_option(tn, nc.WILL, nc.LINEMODE)
    # Exercise DONT/WONT acknowledgements
    nc._on_option(tn, nc.DONT, nc.TTYPE)
    nc._on_option(tn, nc.WONT, nc.TTYPE)
    sent = bytes(tn.sock.sent)
    # Basic sanity: we should have produced multiple IAC negotiation bytes
    assert sent.count(bytes([nc.IAC])) >= 6

