import socket
import logging
import pysnmp.proto.api
from pyasn1.codec.ber import encoder, decoder
from struct import pack, unpack
from time import time

from . import UdpTransport

class SnmpUdpClient(UdpTransport):
    def __init__(self, host, interval, version, community, variables, port=161):
        self._version = {
            '1':  pysnmp.proto.api.protoVersion1,
            '2c': pysnmp.proto.api.protoVersion2c,
        }.get(version, pysnmp.proto.api.protoVersion1)
        self._community = community
        self._vars = variables
        # Protocol verison to use
        self._pmod = pysnmp.proto.api.protoModules[self._version]
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

    def process_data(self, data, tm = None):
        self._retries = 0

        # Process data
        if tm is None:
            tm = time()
        while data:
            msg, data = decoder.decode(data, asn1Spec=self._pmod.Message())
            pdu = self._pmod.apiMessage.getPDU(msg)
            # Check for SNMP errors reported
            error = self._pmod.apiPDU.getErrorStatus(pdu)
            if error:
                logging.critical("SNMP: %s" % error.prettyPrint())
            else:
                try:
                    for oid, val in self._pmod.apiPDU.getVarBinds(pdu):
                        self.on_data(oid, val, tm)
                except Exception as e:
                    logging.critical(e)
        self._state = self.READY
        self.stop()
        return False

    def on_data(self, oid, val, tm):
        pass
