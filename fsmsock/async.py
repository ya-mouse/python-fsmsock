import atexit
import socket, select
from time import time

from .proto import base

class FSMSock():
    def __init__(self):
        self._cli = []
        self._fds = {}
        self._udptrans = None
        self._epoll = select.epoll()
        atexit.register(self.atexit)

    def register(self, client):
        client.register(self)
        self._cli.append(client)

    def unregister(self, client):
        self._cli.remove(client)
        fileno = client.fileno()
        if fileno != -1:
            self._epoll.unregister(fileno)
            del self._fds[fileno]
        client.disconnect()

    def connect(self, client):
        self.register(client)
        client.connect()

    def tick(self, timeout=0.3):
        try:
            events = self._epoll.poll(timeout)
#        except InterruptedError:
        except IOError as e:
            return
        tm = time()
        for fileno, event in events:
            c = self._fds.get(fileno)
            if event & select.EPOLLHUP:
                c.disconnect()
                epoll.unregister(fileno)
                continue
            if event & select.EPOLLOUT:
                if c.request():
                    self._epoll.modify(fileno, select.EPOLLIN)
            if event & select.EPOLLIN:
                if c.process():
                    self._epoll.modify(fileno, select.EPOLLOUT)

        # Iterate over clients
        tm = time()
        for c in self._cli:
            if not c.connected():
                print('Not connected: %s' % c)
                if c.timeouted(tm):
                    print('Timeouted: %s' % c)
                    self.unregister(c)
            """
            if not c.connected():
                if c.timeouted(tm):
                    if isinstance(c, proto.base.UdpClient):
                        c.connect()
                    else:
                        if c.fileno() != -1:
                            del self._fds[c.fileno()]
                        c.connect()
                        if c.fileno() != -1:
                            self._epoll.register(c.fileno(), select.EPOLLOUT)
                            self._fds[c.fileno()] = c
            """
            if c.expired(tm):
                c.queue()

    def run(self):
        return len(self._cli) > 0

    def register_udp(self):
        if self.udp_registered():
            return self._udptrans

        self._udptrans = base.UdpAbstractTransport()
        self._udptrans.register(self)
        self._udptrans.connect()

        return self._udptrans

    def udp_registered(self):
        return not self._udptrans is None

    def atexit(self):
        for c in self._cli:
            try:
                c.disconnect()
            except:
                pass
