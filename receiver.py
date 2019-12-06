import socket
import struct
import binascii
import os
import sys
import random


class STATE:
    WAIT_0 = 0
    WAIT_1 = 1


address = "127.0.0.1"
port = 5002
State = None
PACKET_SIZE = 1024
ACK1 = b"1" * PACKET_SIZE
ACK0 = b"0" * PACKET_SIZE
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('', port))

def checksum(rcvpkt):
    sum = 0
    # convert binary data to hexadecimal for checksum
    data_hex = binascii.hexlify(rcvpkt)
    for i in data_hex:
        sum = sum + int(str(i), 16)
    return sum


def udt_send(sndpkt, address, port):
    s.sendto(sndpkt, (address, port))


def is_ACK(rcvACK, ACK) -> bool:
    seqNum, _, data = extract(rcvACK)
    return seqNum == ACK and data == PACKET_SIZE * str(ACK).encode()


def isCorrupt(rcvACK) -> bool:
    _, chksum, data = extract(rcvACK)
    new_chksum = checksum(data)
    return chksum != new_chksum


def has_seq(expectedseqNum, rcvpkt) -> bool:
    new_seqNum, _, data = extract(rcvpkt) #change here
    return new_seqNum == expectedseqNum  #i change here


def make_pkt(data, seqNum):
    fmt = "!II" + str(PACKET_SIZE) + "s"  # !II1024s network byte order
    chksum = checksum(data)
    return struct.pack(fmt, seqNum, chksum, data)


def rdt_rcv(port):
    pkt, client = s.recvfrom(2048)  # receive as bytes
    if len(pkt) == 4:  # end pkt
        return pkt, client
    if random.random() < error_prob:  # intentionally make error to DATA pkt
        return make_error(pkt), client
    elif random.random() < loss_prob:  # intentionally make loss to DATA pkt
        return None, client
    else:
        return pkt, client


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


def recv(send_to_port, recv_from_port):
    State = STATE.WAIT_0
    data = []
    rcvpkt = None
    sndpkt = None
    seqNum = 0
    client = None
    oncethru = 0
    expectedseqNum = 0
    while True:
        if State == STATE.WAIT_0:
            rcvpkt, client = rdt_rcv(recv_from_port)
            if rcvpkt is None:
                print("pkt loss")
                continue  # DATA pkt loss
            if len(rcvpkt) == 4:  # end pkt
                break
            if isCorrupt(rcvpkt) or has_seq(expectedseqNum, rcvpkt):  # receive fail
                print("Receive failed1")
                sndpkt = make_pkt(ACK1, 1)
                udt_send(sndpkt, client[0], send_to_port)  # resend
            else:
                print("Receive zero")
                oncethru = 1
                data.append(extract(rcvpkt)[2])
                sndpkt = make_pkt(ACK0, 0)
                udt_send(sndpkt, client[0], send_to_port)
                State = STATE.WAIT_1
        elif State == STATE.WAIT_1:
            rcvpkt, client = rdt_rcv(recv_from_port)
            if rcvpkt is None:
                print("pkt loss")
                continue  # DATA pkt loss
            if len(rcvpkt) == 4:
                break
            if isCorrupt(rcvpkt) or has_seq(expectedseqNum, rcvpkt):  # receive fail
                print("Receive failed0")
                sndpkt = make_pkt(ACK0, 0)
                udt_send(sndpkt, client[0], send_to_port)  # resend
            else:
                print("Receive one")
                data.append(extract(rcvpkt)[2])
                sndpkt = make_pkt(ACK1, 1)
                udt_send(sndpkt, client[0], send_to_port)
                expectedseqNum += 1  #add
                State = STATE.WAIT_0
        else:
            exit(1)
    return b"".join(data)


# At receiver side, data is received from port 5002, send to port 5003
if __name__ == "__main__":
    send_to_port = 5003
    recv_from_port = 5002
    error_prob = 0
    if len(sys.argv) == 2:
        error_prob = int(sys.argv[1])/100
    if len(sys.argv) == 3:
        loss_prob = int(sys.argv[2])/100
    data = recv(send_to_port, recv_from_port)
    f = open("recv_image.jpg", "wb+")
    f.write(data)
    f.close()