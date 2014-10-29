import socket, select
from time import time

from .proto import base

class FSMNet():
    def __init__(self):
        self._cli = []
        self._fds = {}
        self._udp = {}
        self._epoll = select.epoll()

    def push(self, client):
        client.set_fsm(self)

    def tick(self, timeout=0.3):
        try:
            events = self._epoll.poll(timeout)
#        except InterruptedError:
        except IOError:
            return
        tm = time()
        for fileno, event in events:
            c = self._fds.get(fileno)
            if c == None:
                # Special handling for UdpClient
                if fileno == proto.base.UdpClient.fileno():
                    c = proto.base.UdpClient.process()
                    if c != None:
                        c.request()
                continue
            if event & select.EPOLLHUP:
                c.disconnect()
                epoll.unregister(fileno)
                continue
            if event & select.EPOLLOUT:
                if c.request():
                    epoll.modify(fileno, select.EPOLLIN)
            if event & select.EPOLLIN:
                if c.process():
                    epoll.modify(fileno, select.EPOLLOUT)

        # Iterate over clients
        tm = time()
        for c in self._cli:
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
            elif c.expired(tm):
                if isinstance(c, proto.base.UdpClient):
                    c.request()
                else:
                    try:
                        self._epoll.modify(c.fileno(), select.EPOLLOUT | select.EPOLLIN)
                    except Exception as e:
                        pass
