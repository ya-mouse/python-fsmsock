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

    def __init__(self, host, interval):
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
        # Make connection within N-seconds depending on current client stack size
        self._expire = time() + (len(self._fsm._cli) / 10.0) % 5.0
        # ...timeout within + 15.0 s
        self._timeout = self._expire + 15.0
        return True

    def disconnect(self):
#        import traceback
        self._retries = 0
        self._expire = time() + 60.0
        self._timeout = self._expire + 15.0
#        print('disconn', self, self._retries, self._state, self._timeout)
        self._state = self.INIT
        self.on_disconnect()
        if self._sock != None:
            self._sock.close()

    def on_disconnect(self):
        self.stop()

    def on_expire(self):
        return True

    def on_timeout(self):
        self.disconnect()
        return False

    def shutdown(self):
        self.disconnect()

    def ready(self):
        return (self._state == self.READY)

    def queue(self):
        if self.fileno() != -1:
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
#                logging.debug("{0}: expired {1}".format(self._host, self._retries))
#            else:
#                logging.debug("{0}: timeouted {1}".format(self._host, self._retries))
            self._state = state
        return True

    def expired(self, tm = None):
        rc = self._check_timers(self._expire, self.EXPIRED, tm)
#        print('is-expired: ', self, rc, (tm-self._expire), self._retries)
        if rc:
            self._retries += 1
            if self._retries >= self._max_retries:
                return self.on_timeout()
            return self.on_expire()
        return rc

    def timeouted(self, tm = None):
        rc = self._check_timers(self._timeout, self.TIMEOUTED, tm)
#        print('is-timeouted: ', self, rc, (tm-self._timeout), self._retries)
        if rc:
            self._retries += 1
            if self._retries >= self._max_retries:
                return self.on_timeout()
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
#        logging.debug("{0}: entering request ({1})".format(self._host, self._state))
        state = self._state
        if self._state == self.WAIT_ANSWER and not self.timeouted():
            return 0
        if tm == None:
            tm = time()
        self._expire = tm + 5.0
#        if state != self.EXPIRED:
        self._timeout = self._expire + 15.0

        size = self.send_buf()
        if size > 0:
            self._state = self.WAIT_ANSWER
        elif size < 0:
            return 0
#        else:
#            logging.debug("{0}: write failed".format(self._host))
#        logging.debug(self._host, ":", self._expire, self._timeout)
        return select.EPOLLIN

    def process(self, nr = None):
        self._retries = 0
        if nr == None:
            nr = self._bufsize
        data = self._read(nr)
        if len(data) == 0:
            return 0
        # If we didn't request anything
        if self._state not in (self.EXPIRED, self.WAIT_ANSWER):
            return 0
        return self.process_data(data)

    def process_data(self, data):
        return 0

    def _write(self, data):
        if self._sock == None:
            return 0
        try:
            result = self._sock.send(data)
            return result
        except (OSError, socket.error) as why:
            if why.args[0] == EWOULDBLOCK:
                return 0
            elif why.args[0] in _DISCONNECTED:
#                print(self, 'DISCONNECTED', why)
                self.disconnect()
                return 0
            else:
#                print(self, why)
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
#                print(self, 'DISCONNECTED', why)
                self.disconnect()
                return ''
            else:
#               raise
#                print(self, why)
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
            self._expire = self._timeout = time() + 15.0
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

    def disconnect(self):
        if self.connected():
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except:
                pass
        super().disconnect()
        self._sock = None

class UdpAbstractTransport(Transport):
    SOCK_BUFSIZE = 8388544

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
#            logging.debug(b, ":", bsize)
            if bsize < UdpAbstractTransport.SOCK_BUFSIZE:
                self._sock.setsockopt(socket.SOL_SOCKET, b, UdpAbstractTransport.SOCK_BUFSIZE)

        self._fsm._fds[self.fileno()] = self
        self._fsm._epoll.register(self.fileno(), select.EPOLLIN)
        return True

    def process(self, nr = None):
        if nr == None:
            nr = 131070
        while True:
            data, sockaddr = self.read(nr)
            if sockaddr == None:
                return -1
            cli = self._cli[sockaddr]
            if len(data) == 0:
                cli.disconnect()
            elif cli._state != Transport.WAIT_ANSWER:
                cli.on_unorder(data)
                continue
            self._expire += 5.0
            self._timeout += 5.0
            if cli.process_data(data):
                cli.request()
        # We don't want EPOLLOUT to be set
        return -1

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

    def on_unorder(self, data):
        logging.warning("{0}: unordered answer [{1}]".format(self, data))
        self.stop()
#        cli.disconnect()
#        cli._unord = True
        #data = ''

class UdpTransport(Transport):
    def __init__(self, host, interval, port):
        self._port = port
        self._sockaddr = None
        self._unord = False
        super().__init__(host, interval)

    def connect(self):
        if self._unord:
            logging.debug('Connecting {0}...'.format(self._host))
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
            logging.debug(e)

        if self._sockaddr == None:
            # Fallback to the generic socket, queue a retry
            self._state = self.INIT
            self._expire = time() + 5.0
            self._timeout = self._expire + 15.0
            return False

        self._state = self.READY
        return True

    def disconnect(self):
        super().disconnect()
#        self._retries = 0
#        self._timeout = 0.0
#        self._state = self.INIT

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
