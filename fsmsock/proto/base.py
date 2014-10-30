from time import time,sleep
from struct import pack, unpack
import os, sys, fcntl, select
import socket, serial
import traceback
import logging

from errno import EALREADY, EINPROGRESS, EWOULDBLOCK, ECONNRESET, EINVAL, \
     ENOTCONN, ESHUTDOWN, EINTR, EISCONN, EBADF, ECONNABORTED, EPIPE, EAGAIN, \
     ECONNREFUSED, ETIMEDOUT, errorcode

_DISCONNECTED = frozenset((ECONNRESET, ENOTCONN, ESHUTDOWN, ECONNABORTED, EPIPE,
                           EBADF, ECONNREFUSED, ETIMEDOUT))

class Transport():
    INIT = 1
    READY = 2
    EXPIRED = 3
    TIMEOUTED = 4
    WAIT_ANSWER = 5
    LAST = WAIT_ANSWER

    def __init__(self, host, interval, logger=logging.getLogger('default')):
        self._fsm = None
        self._sock = None
        self._host = host
        self._interval = interval
        self._buf = None
        self._res = None
        self._retries = 0
        self._max_retries = 5
        self._expire = 0.0
        self._timeout = 0.0
        self._bufsize = 1024

        self._state = self.INIT
        self._l = logger
        self._build_buf()

    def _build_buf(self):
        pass

    def register(self, fsm):
        self._fsm = fsm

    def stop(self):
        self._fsm.unregister(self)

    def connect(self):
        if self.connected():
            return True
        self._expire = 0.0
        self._timeout = time() + 5.0
        return True

    def disconnect(self):
        if self._sock != None:
            self._sock.close()
        self._retries = 0
        self._timeout = time() + 5.0
        self._state = self.INIT

    def ready(self):
        return (self._state == self.READY)

    def queue(self):
        self._fsm._epoll.modify(self.fileno(), select.EPOLLOUT | select.EPOLLIN)

    def _check_timers(self, field, state, tm = None):
        if self._state == self.TIMEOUTED:
            return True
        if tm == None:
            tm = time()
        if field > tm:
            return False
        # Если мы ещё не готовы к работе
#        if field == 0.0:
#            return False
        if self._state != self.INIT:
#            if state == self.EXPIRED:
#                self._l.debug("{0}: expired {1}".format(self._host, self._retries))
#            else:
#                self._l.debug("{0}: timeouted {1}".format(self._host, self._retries))
            self._state = state
        return True

    def expired(self, tm = None):
        rc = self._check_timers(self._expire, self.EXPIRED, tm)
        if rc:
            self._retries += 1
            if self._retries >= self._max_retries:
                self.disconnect()
                return False
        return rc

    def timeouted(self, tm = None):
        rc = self._check_timers(self._timeout, self.TIMEOUTED, tm)
        if rc:
            self._retries += 1
            if self._retries >= self._max_retries:
                self.disconnect()
                return False
        return rc

    def connected(self):
        return not self._state in (self.INIT, self.TIMEOUTED)

    def fileno(self):
        if self._sock == None:
            return -1
        return self._sock.fileno()

    def send_buf(self):
        return self._write(self._buf)

    def request(self, tm = None):
#        self._l.debug("{0}: entering request ({1})".format(self._host, self._state))
        state = self._state
        if self._state == self.WAIT_ANSWER and not self.timeouted():
            return False
        size = self.send_buf()
        if size > 0:
            self._state = self.WAIT_ANSWER
        elif size < 0:
            return False
#        else:
#            self._l.debug("{0}: write failed".format(self._host))
        if tm == None:
            tm = time()
        self._expire = tm + self._interval
#        if state != self.EXPIRED:
        self._timeout = tm + 5.0
#        self._l.debug(self._host, ":", self._expire, self._timeout)
        return True

    def process(self, nr = None):
        self._retries = 0
        if nr == None:
            nr = self._bufsize
        data = self._read(nr)
        if len(data) == 0:
            return ''
        # If we didn't request anything
        if self._state != self.WAIT_ANSWER:
            return ''
        return data

    def _write(self, data):
        if self._sock == None:
            return 0
        try:
            result = self._sock.send(data)
            return result
        except socket.error as why:
            if why.args[0] == EWOULDBLOCK:
                return 0
            elif why.args[0] in _DISCONNECTED:
                self.disconnect()
                return 0
            else:
#               raise
                self.disconnect()
                return 0

    def _read(self, size):
        if self._sock == None:
            return ''
        try:
            result = self._sock.recv(size)
            return result
        except socket.error as why:
            if why.args[0] == EWOULDBLOCK:
                return ''
            elif why.args[0] in _DISCONNECTED:
                self.disconnect()
                return ''
            else:
#               raise
                self.disconnect()
                return ''

class TcpTransport(Transport):
    def __init__(self, host, interval, sock_params):
        self._port = sock_params[2]
        self._sock_params = sock_params
        super().__init__(host, interval)

    def connect(self):
        if self.connected():
            return True

        super().connect()

        try:
            self._sock = None
            for res in socket.getaddrinfo(self._host,
                                          self._port,
                                          0,
                                          self._sock_params[1]):
                self._sockaddr = res[4]
                self._sock = socket.socket(res[0], res[1])
                if self._sock != None:
                    break
        except:
            pass

        if self._sock == None:
            # Fallback to the generic socket, queue a retry
            self._sock = socket.socket(self._sock_params[0], self._sock_params[1])
            self._state = self.INIT
            self._expire = self._timeout = time() + 5.0
            return False

        self._fsm._fds[self.fileno()] = self
        self._fsm._epoll.register(self.fileno(), select.EPOLLIN)

        self._sock.setblocking(0)

        if res[1] == socket.SOCK_STREAM:
            for level, name, val in ((socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
                                     (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
                                     (socket.IPPROTO_IP, socket.IP_TOS, 0x10)):
                self._sock.setsockopt(level, name, val)

        if len(self._sock_params) == 4:
            self._bufsize = self._sock_params[3]
            for b in socket.SO_RCVBUF, socket.SO_SNDBUF:
                bsize = self._sock.getsockopt(socket.SOL_SOCKET, b)
                if bsize < self._bufsize:
                    self._sock.setsockopt(socket.SOL_SOCKET, b, self._bufsize)

        err = self._sock.connect_ex((self._host, self._port))
        if err in (EINPROGRESS, EALREADY, EWOULDBLOCK) \
        or err == EINVAL and os.name in ('nt', 'ce'):
            self._state = self.READY
            return True
        if err in (0, EISCONN):
            self._state = self.READY
            return True
        if err in _DISCONNECTED:
            self._state = self.INIT
            return False
        else:
            self._state = self.INIT
            return False # raise socket.error(err, errorcode[err])
            # return False

class UdpAbstractTransport(Transport):
    def __init__(self):
        self._cli = {}
        super().__init__(None, 0.0)

    def connect(self):
        if self.connected():
            return True

        self._sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        for b in socket.SO_RCVBUF, socket.SO_SNDBUF:
            bsize = self._sock.getsockopt(socket.SOL_SOCKET, b)
#            self._l.debug(b, ":", bsize)
            if bsize < 8388544:
                self._sock.setsockopt(socket.SOL_SOCKET, b, 8388544)

        self._fsm._fds[self.fileno()] = self
        self._fsm._epoll.register(self.fileno(), select.EPOLLIN)
        return True

    def process(self, nr = None):
        if nr == None:
            nr = 131070
        data, sockaddr = self.read(nr)
        if sockaddr == None:
            return None
        cli = self._cli[sockaddr]
        if len(data) == 0:
            cli.disconnect()
        elif cli._state != Transport.WAIT_ANSWER:
            cli.disconnect()
            cli._unord = True
            cli._l.warning("{0}: unordered answer".format(cli._host))
            #data = ''
            return None
        if cli.process_data(data):
            cli.request()
        # We don't want EPOLLOUT to be set
        return None

    def read(self, size):
        try:
            result = self._sock.recvfrom(size)
            return result
        except socket.error as why:
            if why.args[0] == EWOULDBLOCK:
                return ('', None)
            elif why.args[0] in _DISCONNECTED:
                return ('', None)
            else:
                return ('', None)

    def request(self, tm = None):
        return False

class UdpTransport(Transport):
    def __init__(self, host, interval, port):
        self._port = port
        self._sockaddr = None
        self._unord = False
        super().__init__(host, interval)

    def connect(self):
        if self._unord:
            self._l.debug('Connecting {0}...'.format(self._host))
            self._unord = False
        if self.connected():
            return True

        super().connect()

        self._udp = self._fsm.register_udp()

        if self._sockaddr != None:
            try:
                del self._udp._cli[self._sockaddr]
            except:
                pass

        try:
            for res in socket.getaddrinfo(self._host,
                                          self._port,
                                          0,
                                          socket.SOCK_DGRAM):
                if res[0] == socket.AF_INET6 and False:
                    i = res[4][0].find(':ffff:')
                    if i != -1:
                        addr = res[4][0][i+8:].split(':')
                        addr = [int(x, base=16) for x in addr]
                        self._sockaddr = ('::ffff:%d.%d.%d.%d' % (addr[0] >> 8, addr[0] & 0xff, addr[1] >> 8, addr[1] & 0xff),
                                          res[4][1], res[4][2], res[4][3])
                else:
                    if res[0] == socket.AF_INET:
                        self._sockaddr = ('::ffff:'+res[4][0], res[4][1], 0, 0)
                    else:
                        self._sockaddr = res[4]
                self._udp._cli[self._sockaddr] = self
                break
        except Exception as e:
            self._l.critical(e)

        if self._sockaddr == None:
            # Fallback to the generic socket, queue a retry
            self._state = self.INIT
            self._expire = self._timeout = time() + 5.0
            return False

        self._state = self.READY
        return True

    def disconnect(self):
        self._retries = 0
        self._timeout = 0.0
        self._state = self.INIT

    def queue(self):
        self.request()

    def fileno(self):
        # Always return `-1' instead of _udp.fileno() to keep UDP FD
        return -1

    @property
    def sockaddr(self):
        return self._sockaddr

    def process_data(self, data):
        self._retries = 0
        return False

    def _write(self, data):
        if data is None:
            return 0
        try:
            result = self._udp._sock.sendto(data, self._sockaddr)
            if result < 0:
                return 0
            return result
        except socket.error as why:
            if why.args[0] == EWOULDBLOCK:
                return 0
            elif why.args[0] in _DISCONNECTED:
                self.disconnect()
                return 0
            else:
                self.disconnect()
                return 0

    def _read(self, size):
        return ''

class SerialTransport(Transport):
    def __init__(self, host, interval, serial):
        self._serial = serial
        super().__init__(host, interval)

    def connect(self):
        if self.connected():
            return True
        cfg = self._serial
        self._sock = serial.Serial(self._host, timeout=0.05, baudrate=cfg['baud'], bytesize=cfg['bits'], parity=cfg['parity'], stopbits=cfg['stop'])
        flags = fcntl.fcntl(self._sock.fileno(), fcntl.F_GETFL, 0)
        flags |= os.O_NONBLOCK
        fcntl.fcntl(self._sock.fileno(), fcntl.F_SETFL, flags)
        return super().connect()

    def _write(self, data):
        if self._sock == None:
            return 0
        try:
            result = self._sock.write(data)
            return result
        except socket.error as why:
            if why.args[0] == EWOULDBLOCK:
                return 0
            elif why.args[0] in _DISCONNECTED:
                self.disconnect()
                return 0
            else:
                self.disconnect()
                return 0

    def _read(self, size):
        if self._sock == None:
            return ''
        try:
            result = self._sock.read(size)
            return result
        except socket.error as why:
            if why.args[0] == EWOULDBLOCK:
                return ''
            elif why.args[0] in _DISCONNECTED:
                self.disconnect()
                return ''
            else:
                self.disconnect()
                return ''
