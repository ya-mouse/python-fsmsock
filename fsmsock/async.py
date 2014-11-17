import atexit
import logging
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
        try:
            self._cli.remove(client)
            fileno = client.fileno()
            if fileno != -1:
                self._epoll.unregister(fileno)
                del self._fds[fileno]
        except:
            pass
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
                c.on_disconnect()
                continue
            if event & select.EPOLLIN:
                flags = c.process()
                if flags != -1:
#                    logger.debug('PROCESS.{0}'.format(flags))
                    if c.connected():
                        self._epoll.modify(fileno, flags)
            if event & select.EPOLLOUT:
                flags = c.request(tm)
                if flags != -1:
#                    logger.debug('REQUEST.{0} {1}'.format(c.connected(), flags))
                    if c.connected():
                        self._epoll.modify(fileno, flags)

        # Iterate over clients
        tm = time()
        for c in self._cli:
            if c.timeouted(tm):
#                logger.debug('Timeouted: {0}'.format(c))
                if not c.connected():
#                    logger.debug('Not connected: {0}'.format(c))
                    c.on_disconnect()
            elif c.expired(tm):
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
        atexit.unregister(self.atexit)
        for c in self._cli:
            try:
                c.disconnect()
            except:
                pass
