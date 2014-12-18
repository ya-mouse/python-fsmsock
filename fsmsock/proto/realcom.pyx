from struct import pack, unpack
import socket
import select
import logging

from . import TcpTransport

aspp_bits = {
    5 : 0,
    6 : 1,
    7 : 2,
    8 : 3,
}

aspp_stop = {
    1 : 0,
    2 : 4,
}

aspp_parity = {
    'E' : 8,
    'O' : 16,
    'M' : 24,
    'S' : 32,
    'N' : 0,
}

aspp_bauds = {
    300    : 0,
    600    : 1,
    1200   : 2,
    2400   : 3,
    4800   : 4,
    7200   : 5,
    9600   : 6,
    19200  : 7,
    38400  : 8,
    57600  : 9,
    115200 : 10,
    230400 : 11,
    460800 : 12,
    921600 : 13,
}

CMD_PORT_INIT   = 44
CMD_POLLING     = 39
CMD_ALIVE       = 40
CMD_TX_FIFO     = 48

aspp_commands = {
    19 : 5,     # CMD_LSTATUS
    CMD_PORT_INIT : 5, # CMD_PORT_INIT

    38 : 4,     # CMD_NOTIFY
    47 : 4,     # CMD_WAIT_OQUEUE
    21 : 4,     # CMD_IQUEUE
    22 : 4,     # CMD_OQUEUE

    16 : 3,     # CMD_IOCTL
    17 : 3,     # CMD_FLOWCTRL
    18 : 3,     # CMD_LINECTRL
    20 : 3,     # CMD_FLUSH
    23 : 3,     # CMD_SETBAUD
    24 : 3,     # CMD_XONXOFF
    33 : 3,     # CMD_START_BREAK
    34 : 3,     # CMD_STOP_BREAK
    36 : 3,     # CMD_START_NOTIFY
    37 : 3,     # CMD_STOP_NOTIFY
    43 : 3,     # CMD_HOST
    CMD_TX_FIFO : 3,     # CMD_TX_FIFO
    51 : 3,     # CMD_SETXON
    52 : 3,     # CMD_SETXOFF
}

class _RealcomCmdClient(TcpTransport):
    CONFIGURED = TcpTransport.LAST + 1

    def __init__(self, client, port, cfg):
        self._client = client
        self._port = port
        self._cfg = cfg
        super().__init__(client._host, client._interval,
                         (socket.AF_INET, socket.SOCK_STREAM, 16 + self._port))

    def _init_port(self):
        mode = aspp_bits.get(self._cfg['bits'], aspp_bits[8])
        mode |= aspp_parity.get(self._cfg['parity'], aspp_parity['N'])
        baud = aspp_bauds.get(self._cfg['baud'], aspp_bauds[9600])

        uart_mcr_dtr = 0
        uart_mcr_rts = 0
        crtscts = 0
        ixon = 0
        ixoff = 0
        cmd = pack('10B3B', CMD_PORT_INIT, 8, baud, mode,
                          uart_mcr_dtr, uart_mcr_rts, crtscts, crtscts,
                          ixon, ixoff,
                          CMD_TX_FIFO, 16, 16)
        self._state = self.WAIT_ANSWER
        self._write(cmd)

    def process_data(self, data):
        flags = 0
        nr = 0
        i = 0
        size = len(data)
        while (size):
#            logging.debug(data[i])
            if data[i] == CMD_POLLING:
                if size < 3:
                    size = 0
                    continue
                cmd = pack('3B', CMD_ALIVE, 1, data[i+2])
#                logging.debug("CMD:",cmd)
                nr = self._write(cmd)
                flags = select.EPOLLIN
            else:
                try:
                    nr = aspp_commands[data[i]]
                    if data[i] == CMD_PORT_INIT:
                        self._state = self.CONFIGURED
                except:
                    nr = size

            i += nr
            size -= nr

        return flags

    def expired(self, tm = None):
        return False

    def timeouted(self, tm = None):
        return False

    def ready(self):
        return self._state == self.CONFIGURED

    def request(self, tm = None):
        if self._state == self.READY:
            self._init_port()
            return select.EPOLLIN
        return 0

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

    def ready(self):
        return self._cmd.ready() and super().ready()
