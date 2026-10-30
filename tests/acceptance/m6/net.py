#!/usr/bin/env python3
"""M6 network acceptance for rzv2l-smarc: Ethernet through the ravb driver.

Usage: net.py OUTDIR --tier g0|g1

ETH0 is attached to QEMU's user-mode network (slirp: an isolated private
network, 10.0.2.0/24, no host interface, no physical LAN); the host side
of each transfer is a server on 127.0.0.1, which the guest reaches as
10.0.2.2. With the kernel and DTB of the tier and the BusyBox initramfs:
  boot:     both MACs and PHYs probe; ETH0's link comes up 1 Gb/s full
            duplex; ETH1 has no cable and stays down
  dhcp:     udhcpc obtains a lease on eth0
  sizes:    ICMP echo with payloads 0-1472 bytes (frames 60-1514 bytes)
  down:     a random file of 3 MiB + 1 byte, host -> guest (HTTP, wget)
  up:       a random file of 3 MiB + 3 bytes, guest -> host (nc); both
            SHA-256 equal on each side; more frames than the RX ring
            (1024) and the TX ring (64 frames) hold, both ways
  link:     QMP set_link off: the guest reports link down; on: link up
            1 Gb/s again, and a transfer still matches
  ifdown:   ip link set eth0 down/up: the driver stops and restarts the
            DMAC; DHCP and a transfer again
  reset:    QMP system_reset: the guest boots again; DHCP and a transfer
Writes OUTDIR/serial.log, qemu.log. Exit 0 only if every check passes.
QEMU binary: $QEMU.
"""
import hashlib
import http.server
import json
import os
import re
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "m3"))
from shell import Serial, BOOT_TIMEOUT  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "guests", "out")
INITRD = os.path.join(OUT, "g0", "initramfs.cpio.gz")
DOWN_SIZE = 3 * 1024 * 1024 + 1
UP_SIZE = 3 * 1024 * 1024 + 3
PING_SIZES = [0, 1, 17, 18, 46, 63, 64, 500, 1000, 1471, 1472]
HOST = "10.0.2.2"
# udhcpc's hook: set the address and default route of the lease
DHCP_SCRIPT = ("#!/bin/sh\\n[ \\\"\\$1\\\" = bound ] || exit 0\\n"
               "ip addr flush dev \\$interface\\n"
               "ip addr add \\$ip/\\$mask dev \\$interface\\n"
               "ip route replace default via \\$router\\n")

failures = 0


def check(ok, what):
    global failures
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        failures += 1
    return ok


class Payload:
    """The host side: an HTTP server for host -> guest, a TCP sink for
    guest -> host"""

    def __init__(self):
        self.down = os.urandom(DOWN_SIZE)
        self.received = []
        data = self.down

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.http = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.http_port = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.sink = socket.socket()
        self.sink.bind(("127.0.0.1", 0))
        self.sink.listen(4)
        self.sink_port = self.sink.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            conn, _ = self.sink.accept()
            buf = bytearray()
            while True:
                b = conn.recv(65536)
                if not b:
                    break
                buf += b
            conn.close()
            self.received.append(bytes(buf))


class Qmp:
    def __init__(self, path):
        self.s = socket.socket(socket.AF_UNIX)
        for _ in range(100):
            try:
                self.s.connect(path)
                break
            except OSError:
                time.sleep(0.1)
        self.f = self.s.makefile("rw")
        self.f.readline()
        self.cmd("qmp_capabilities")

    def cmd(self, execute, **args):
        self.f.write(json.dumps({"execute": execute, "arguments": args}) +
                     "\n")
        self.f.flush()
        while True:
            r = json.loads(self.f.readline())
            if "return" in r or "error" in r:
                return r


def run(s, command, timeout=120):
    """Run @command; return its output, None on a timeout"""
    mark = "M6-" + secrets.token_hex(4)
    pos = len(s.buf)
    s.send("%s; echo %s-$((6*7))" % (command, mark))
    if s.wait(re.escape(mark) + r"-42\b", timeout, pos) is None:
        return None
    return s.buf[pos:]


def dhcp(s, what):
    o = run(s, "printf \"%s\" > /tmp/dhcp.sh; chmod +x /tmp/dhcp.sh; "
            "udhcpc -i eth0 -n -q -t 10 -T 2 -s /tmp/dhcp.sh; "
            "ip -4 addr show eth0" % DHCP_SCRIPT, 120)
    return check(o is not None and "lease of 10.0.2.15 obtained" in o and
                 "inet 10.0.2.15/24" in o, "%s: udhcpc lease 10.0.2.15" % what)


def sha256_of(o):
    m = re.search(r"^([0-9a-f]{64})  ", o or "", re.M)
    return m.group(1) if m else None


def transfer(s, payload, what):
    """Both directions; True if both hashes match"""
    want = hashlib.sha256(payload.down).hexdigest()
    o = run(s, "rm -f /tmp/down.bin; wget -q -O /tmp/down.bin "
            "http://%s:%d/f && sha256sum /tmp/down.bin"
            % (HOST, payload.http_port), 300)
    ok_down = check(sha256_of(o) == want, "%s: %d bytes host -> guest, "
                    "SHA-256 equal" % (what, DOWN_SIZE))
    n = len(payload.received)
    o = run(s, "head -c %d /dev/urandom > /tmp/up.bin; sha256sum /tmp/up.bin;"
            " nc -w 5 %s %d < /tmp/up.bin" % (UP_SIZE, HOST,
                                             payload.sink_port), 300)
    got = sha256_of(o)
    for _ in range(100):
        if len(payload.received) > n:
            break
        time.sleep(0.1)
    sent = payload.received[n] if len(payload.received) > n else b""
    ok_up = check(got is not None and len(sent) == UP_SIZE and
                  hashlib.sha256(sent).hexdigest() == got,
                  "%s: %d bytes guest -> host, SHA-256 equal (host got %d)"
                  % (what, UP_SIZE, len(sent)))
    return ok_down and ok_up


def counters(s):
    o = run(s, "cat /sys/class/net/eth0/statistics/rx_packets "
            "/sys/class/net/eth0/statistics/tx_packets "
            "/sys/class/net/eth0/statistics/rx_errors "
            "/sys/class/net/eth0/statistics/tx_errors")
    n = [int(x) for x in re.findall(r"^(\d+)\r?$", o or "", re.M)]
    return n if len(n) == 4 else None


def irq_count(s, name):
    """The sum of both CPUs' counts of the /proc/interrupts line @name"""
    o = run(s, "cat /proc/interrupts") or ""
    m = re.search(r"^\s*\d+:\s+(\d+)\s+(\d+)\s+%s" % name, o, re.M)
    return int(m.group(1)) + int(m.group(2)) if m else 0


def main():
    out = sys.argv[1]
    tier = sys.argv[3] if sys.argv[2:3] == ["--tier"] else "g0"
    os.makedirs(out, exist_ok=True)
    kernel = os.path.join(OUT, tier, "linux", "arch", "arm64", "boot",
                          "Image")
    dtb = os.path.join(OUT, tier, "r9a07g054l2-smarc.dtb")
    sock = os.path.join(out, "serial.sock")
    qmp_path = os.path.join(out, "qmp.sock")
    for f in (sock, qmp_path, os.path.join(out, "qemu.log")):
        if os.path.exists(f):
            os.unlink(f)
    payload = Payload()
    cmd = [os.environ["QEMU"], "-M", "rzv2l-smarc", "-kernel", kernel,
           "-dtb", dtb, "-initrd", INITRD, "-display", "none", "-nodefaults",
           "-chardev", "socket,id=scif0,path=%s,server=on,wait=on" % sock,
           "-serial", "chardev:scif0",
           "-qmp", "unix:%s,server=on,wait=off" % qmp_path,
           "-netdev", "user,id=net0",
           "-net", "nic,netdev=net0,macaddr=02:52:56:00:00:01",
           "-d", "unimp,guest_errors,invalid_mem",
           "-D", os.path.join(out, "qemu.log")]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    log = open(os.path.join(out, "serial.log"), "w")
    s = Serial(sock, log)
    qmp = Qmp(qmp_path)
    try:
        if not check(s.wait(r"G0-INIT: ready", BOOT_TIMEOUT) is not None,
                     "boot: /init runs"):
            return 1
        for i, base in enumerate(("11c20000", "11c30000")):
            check(re.search(r"ravb %s\.ethernet eth%d: Base address at 0x%s"
                            % (base, i, base), s.buf) is not None,
                  "boot: ravb probes ETH%d" % i)
            check(re.search(r"KSZ9131 Gigabit PHY %s\.ethernet-ffffffff:07: "
                            r"attached PHY driver" % base, s.buf) is not None
                  or run(s, "test -e /sys/bus/mdio_bus/devices/"
                         "%s.ethernet-ffffffff:07 && echo PHY-OK" % base)
                  is not None, "boot: KSZ9131 PHY at address 7 on ETH%d" % i)
        o = run(s, "ip link set eth0 up; sleep 2; dmesg | grep -i ravb")
        check(o is not None and "eth0: Link is Up - 1Gbps/Full" in o,
              "boot: eth0 link up, 1 Gb/s full duplex")
        check(o is not None and "11c20000.ethernet eth0: Base address at "
              "0x11c20000, 02:52:56:00:00:01" in o,
              "boot: eth0 has the NIC's MAC address (U-Boot's DT edit)")
        o = run(s, "ip link set eth1 up; sleep 2; ip link show eth1; "
                "ip link set eth1 down")
        check(o is not None and "NO-CARRIER" in o,
              "boot: eth1 has no cable: NO-CARRIER")
        dhcp(s, "dhcp")

        for n in PING_SIZES:
            o = run(s, "ping -c 1 -W 5 -s %d %s" % (n, HOST), 30)
            check(o is not None and "1 packets received" in o,
                  "sizes: ping payload %d bytes (frame %d bytes)"
                  % (n, max(60, 14 + 20 + 8 + n)))
        before = counters(s)
        transfer(s, payload, "transfer")
        after = counters(s)
        if check(before is not None and after is not None,
                 "transfer: eth0 counters read"):
            rx, tx = after[0] - before[0], after[1] - before[1]
            check(rx > 1024 and tx > 1024, "transfer: %d frames received, "
                  "%d sent: beyond one turn of the RX ring (1024) and the "
                  "TX ring (64)" % (rx, tx))
            check(after[2] == 0 and after[3] == 0,
                  "transfer: no rx/tx errors (%d, %d)" % tuple(after[2:]))
        check(irq_count(s, r"GICv3 116 Level\s+11c20000\.ethernet\r?$") > 0,
              "transfer: eth0 interrupts (GIC SPI 84) counted")

        # Link down/up through the backend: PHY interrupt -> IRQC -> GIC
        pos = len(s.buf)
        qmp.cmd("set_link", name="net0", up=False)
        check(s.wait(r"eth0: Link is Down", 30, pos) is not None,
              "link: set_link off -> the guest reports link down")
        pos = len(s.buf)
        qmp.cmd("set_link", name="net0", up=True)
        check(s.wait(r"eth0: Link is Up - 1Gbps/Full", 30, pos) is not None,
              "link: set_link on -> link up again, 1 Gb/s full duplex")
        check(irq_count(s, r"rzg2l-irqc\s+3 Level\s+11c20000\."
                        r"ethernet-ffffffff:07") > 0,
              "link: PHY interrupts (IRQC IRQ2) counted")
        transfer(s, payload, "link")

        # Interface down/up: the driver stops and restarts the DMAC
        o = run(s, "ip link set eth0 down; sleep 1; ip link set eth0 up; "
                "sleep 3; ip link show eth0")
        check(o is not None and "LOWER_UP" in o,
              "ifdown: eth0 down/up, link back")
        dhcp(s, "ifdown")
        transfer(s, payload, "ifdown")

        # Machine reset
        pos = len(s.buf)
        qmp.cmd("system_reset")
        if check(s.wait(r"G0-INIT: ready", BOOT_TIMEOUT, pos) is not None,
                 "reset: the guest boots again"):
            run(s, "ip link set eth0 up; sleep 3")
            dhcp(s, "reset")
            transfer(s, payload, "reset")
    finally:
        proc.kill()
        proc.wait()
        log.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
