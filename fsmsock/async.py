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
#        self._stats = { 'c': 0, 's': { 1:0, 2:0,3:0,4:0,5:0 }, 'i': 0, 'tm': 0 }
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

        tm = time()

        # Init stats counters
#        self._stats['i'] += 1
#        if tm >= self._stats['tm']:
#            i = self._stats['i']
#            self._stats = { 'c': 0, 's': { 1:0, 2:0,3:0,4:0,5:0 }, 'i': i, 'tm': tm }

        # Iterate over clients
        for c in self._cli:
            if not c.timeouted(tm) and c.expired(tm):
                if not c.connected(): # might be just c.connect() and check for `opt_autoreconnect' option
                    c.connect()
                c.queue()
#            self._stats['s'][c._state] += 1

        # Display stats
#        if tm >= self._stats['tm']:
#            self._stats['c'] = len(self._cli)
#            logging.info('STATS: {0}'.format(self._stats))
#            self._stats = { 'c': 0, 's': { 1:0, 2:0,3:0,4:0,5:0 }, 'i': 0, 'tm': tm+30.0 }

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
                c.shutdown()
            except:
                pass
