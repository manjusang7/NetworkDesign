import socket
import struct
import binascii
import os
import sys
import struct
import random
import time
import threading


class STATE:
    WAIT_CALL_0 = 1
    WAIT_ACK_0 = 2
    WAIT_CALL_1 = 3
    WAIT_ACK_1 = 4


State = 0
t = 0
sndpkt = None
PACKET_SIZE = 1024
timeout = 0.05
event = threading.Event()


# Packet format includes sequence number, checksum and payload
# sequence number: 4 bytes, decoded to integer 0 or 1
# checksum: 4 bytes, decoded to integer
# payload: 1024 bytes, decoded to bytes
#
# struct {
#     unsigned int seqNum;
#     unsigned int checksum;
#     char[PACKET_SIZE] data;
# }
#
# For ACK1 packet, its data field is filled with 1
# For ACK0 packet, its data field is filled with 0


def readFile(filename) -> bytes:
    with open(filename, "rb") as f:
        payload = f.read()
        return payload


def timer():                                                    # another thread for timer
    global sndpkt, address, send_to_port, t, timeout
    # wait for green light from the main thread
    event.wait()
    couting_time = time.time()
    while event.is_set():
        if (time.time() - couting_time) > timeout: # timeout
            udt_send(sndpkt, address, send_to_port)  # resend
            print("resend due to timeout")
            couting_time = time.time()


def data_iter(data):
    i = 0
    while i+PACKET_SIZE <= len(data):
        yield data[i:i+PACKET_SIZE]
        i += PACKET_SIZE
    padding_size = PACKET_SIZE - len(data) + i
    if padding_size > 0:
        yield data[i:] + b'0' * padding_size


def checksum(pkt) -> int:
    sum = 0
    # convert binary data to hexadecimal for checksum
    data_hex = binascii.hexlify(pkt)
    for i in data_hex:
        sum = sum + int(str(i), 16)
    return sum


def make_pkt(data, seqNum) -> bytes:
    fmt = "!II" + str(PACKET_SIZE) + "s"  # !II1024s network byte order
    chksum = checksum(data)
    return struct.pack(fmt, seqNum, chksum, data)


def rdt_send(data, address, port) -> bytes:
    if State == STATE.WAIT_CALL_0:
        seqNum = 0
    elif State == STATE.WAIT_CALL_1:
        seqNum = 1
    else:
        exit(1)  # Unexpected error
    sndpkt = make_pkt(data, seqNum)
    udt_send(sndpkt, address, port)
    return sndpkt


def rdt_rcv(address, port) -> bytes:
    global error_prob
    global loss_prob
    rcvpkt, _ = s.recvfrom(2048)
    if random.random() < error_prob:  # intentionally make error to ACK pkt
        return make_error(rcvpkt)
    elif random.random() < loss_prob:  # intentionally make loss to ACK pkt
        return None
    else:
        return rcvpkt


def make_error(pkt) -> bytes:
    temp = bytearray(pkt)
    for i in range(3):
        pos = int(random.random()*len(pkt))
        temp[pos] = temp[pos] >> i
    return bytes(temp)


def extract(pkt):
    # Extract the packet into sequence number, checksum and data payload
    fmt = "!II" + str(PACKET_SIZE) + "s"  # !II1024s network byte order
    seqNum, chksum, data = struct.unpack(fmt, pkt)
    return seqNum, chksum, data


def udt_send(sndpkt, address, port):
    s.sendto(sndpkt, (address, port))


def is_ACK(rcvACK, ACK) -> bool:
    seqNum, _, data = extract(rcvACK)
    return seqNum == ACK and data == PACKET_SIZE * str(ACK).encode()


def isCorrupt(rcvACK) -> bool:
    _, chksum, data = extract(rcvACK)
    new_chksum = checksum(data)
    return chksum != new_chksum


def send(data, address, send_to_port, recv_from_port):
    it = data_iter(data)
    global State, sndpkt, t
    State = STATE.WAIT_CALL_0
    print("Start sending")
    while True:
        try:
            if State == STATE.WAIT_CALL_0:
                sndpkt = rdt_send(next(it), address, send_to_port)
                State = STATE.WAIT_ACK_0
                t += 1
                print("Packet No." + str(t) + " sent.")
            elif State == STATE.WAIT_CALL_1:
                sndpkt = rdt_send(next(it), address, send_to_port)
                State = STATE.WAIT_ACK_1
                t += 1
                print("Packet No." + str(t) + " sent.")
            elif State == STATE.WAIT_ACK_0:
                t1 = threading.Thread(target=timer, daemon=True)
                t1.start()                                       # start the timer
                event.set()                                     # green light for timer
                rcvACK = rdt_rcv(address, recv_from_port)
                if rcvACK == None: # timeout
                    time.sleep(0.04)
                elif is_ACK(rcvACK, 0) and not isCorrupt(rcvACK):  # Successful send
                    State = STATE.WAIT_CALL_1
                else:
                    print("Resend Packet No." + str(t))
                    udt_send(sndpkt, address, send_to_port)     # resend
                event.clear()                                  # red light for timer
            elif State == STATE.WAIT_ACK_1:
                t1 = threading.Thread(target=timer, daemon=True)
                t1.start()                                       # start the waiting timer
                event.set()                                     # green light for timer
                rcvACK = rdt_rcv(address, recv_from_port)
                if rcvACK == None: # timeout
                    time.sleep(0.04)
                elif is_ACK(rcvACK, 1) and not isCorrupt(rcvACK):  # Successful send
                    State = STATE.WAIT_CALL_0
                else:
                    print("Resend Packet No." + str(t))
                    udt_send(sndpkt, address, send_to_port)      # resend
                event.clear()                                   # red light for timer
            else:
                exit(1)  # Unexpected error

        except StopIteration:
            udt_send(b"0000", address, send_to_port)  # end packet
            print("Send finish")
            break  # All data sent

# At sender side, data is sent to port 5002, received at port 5003


if __name__ == "__main__":
    address = "127.0.0.1"
    send_to_port = 5002
    recv_from_port = 5003
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((address, recv_from_port))
    error_prob = 0
    loss_prob = 0
    if len(sys.argv) == 3:
        error_prob = int(sys.argv[2])/100
    elif len(sys.argv) == 4:
        loss_prob = int(sys.argv[3])/100
    print(len(sys.argv))
    filename = sys.argv[1]
    r = readFile(filename)
    start_time = time.time()
    send(r, address, send_to_port, recv_from_port)
    print("Transmission time:", time.time() - start_time, "s")
    s.close()
