bits = {
    5 : 0,
    6 : 1,
    7 : 2,
    8 : 3,
}

stop = {
    1 : 0,
    2 : 4,
}

parity = {
    'E' : 8,
    'O' : 16,
    'M' : 24,
    'S' : 32,
    'N' : 0,
}

bauds = {
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

commands = {
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
