import socket
import pysnmp.proto.api
from pyasn1.codec.ber import encoder, decoder
from struct import pack, unpack
from time import time

from . import UdpTransport

class SnmpUdpClient(UdpTransport):
    def __init__(self, host, interval, proto, community, variables, port=161):
        self._proto = {
            '1':  pysnmp.proto.api.protoVersion1,
            '2c': pysnmp.proto.api.protoVersion2c,
        }.get(proto, pysnmp.proto.api.protoVersion1)
        self._community = community
        self._vars = variables
        # Protocol verison to use
        self._pmod = pysnmp.proto.api.protoModules[self._proto]
        self._value = None
        super().__init__(host, interval, port)

    def _build_buf(self):
        # Build PDU
        pdu = self._pmod.GetRequestPDU()
        self._pmod.apiPDU.setDefaults(pdu)
        self._pmod.apiPDU.setVarBinds(pdu, ( (v, self._pmod.Null('')) for v in self._vars) )
        # Build message
        msg = self._pmod.Message()
        self._pmod.apiMessage.setDefaults(msg)
        self._pmod.apiMessage.setCommunity(msg, self._community)
        self._pmod.apiMessage.setPDU(msg, pdu)

        self._buf = encoder.encode(msg)

    def process_data(self, data):
        self._retries = 0
        if len(data) == 0:
            return False

        # Process data
        tm = time()
        while data:
            msg, data = decoder.decode(data, asn1Spec=self._pmod.Message())
            pdu = self._pmod.apiMessage.getPDU(msg)
            # Check for SNMP errors reported
            error = self._pmod.apiPDU.getErrorStatus(pdu)
            if error:
                self._l.critical("SNMP: %s" % error.prettyPrint())
            elif not self._value is None:
                try:
                    for oid, val in self._pmod.apiPDU.getVarBinds(pdu):
                        self._value(oid, val, tm)
                except Exception as e:
                    self._l.critical(e)
        self._state = self.READY
        self.stop()
        return False
