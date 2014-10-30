from struct import pack, unpack
import socket

from . import TcpTransport
from . import _aspp as aspp

class _RealcomCmdClient(TcpTransport):
    CONFIGURED = TcpTransport.LAST + 1

    def __init__(self, client, port, cfg):
        self._client = client
        self._port = port
        self._cfg = cfg
        super().__init__(client._host, client._interval,
                         (socket.AF_INET, socket.SOCK_STREAM, 16 + self._port))

    def _init_port(self):
        mode = aspp.bits.get(self._cfg['bits'], aspp.bits[8])
        mode |= aspp.parity.get(self._cfg['parity'], aspp.parity['N'])
        baud = aspp.bauds.get(self._cfg['baud'], aspp.bauds[9600])

        uart_mcr_dtr = 0
        uart_mcr_rts = 0
        crtscts = 0
        ixon = 0
        ixoff = 0
        cmd = pack('10B3B', aspp.CMD_PORT_INIT, 8, baud, mode,
                          uart_mcr_dtr, uart_mcr_rts, crtscts, crtscts,
                          ixon, ixoff,
                          aspp.CMD_TX_FIFO, 16, 16)
        self._state = self.WAIT_ANSWER
        self._write(cmd)

    def _process_cmd(self, data):
        rc = False
        nr = 0
        i = 0
        size = len(data)
        while (size):
#            self._l.debug(data[i])
            if data[i] == aspp.CMD_POLLING:
                if size < 3:
                    size = 0
                    continue
                cmd = pack('3B', aspp.CMD_ALIVE, 1, data[i+2])
#                self._l.debug("CMD:",cmd)
                nr = self._write(cmd)
                rc = True
            else:
                try:
                    nr = aspp.commands[data[i]]
                    if data[i] == aspp.CMD_PORT_INIT:
                        self._state = self.CONFIGURED
                except:
                    nr = size

            i += nr
            size -= nr

        return rc

    def expired(self, tm = None):
        return False

    def timeouted(self, tm = None):
        return False

    def ready(self):
        return self._state == self.CONFIGURED

    def request(self, tm = None):
        if self._state == self.READY:
            self._init_port()
        return True

    def process(self):
        data = super().process()
        if len(data) == 0:
            return False
        return self._process_cmd(data)

class RealcomClient(TcpTransport):
    def __init__(self, host, interval, port, cfg):
        super().__init__(host, interval)
        self._cmd = _RealcomCmdClient(self, port, cfg)

    def connect(self):
        if self.connected():
            return True
        self._bufidx = 0
        return super().connect()

    def send_buf(self):
        if self._cmd.ready():
            return self._write(self._buf[self._bufidx])
        return 0

    def cmd(self):
        return self._cmd

    def ready():
        return self._cmd.ready() and super().ready()
