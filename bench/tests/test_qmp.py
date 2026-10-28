# SPDX-License-Identifier: GPL-2.0-or-later
"""A QMP reply that arrives after its caller timed out must not kill the client."""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import QMP  # noqa: E402


async def fake_qemu(r, w):
    w.write(b'{"QMP": {}}\n')
    await w.drain()
    await r.readline()                                  # qmp_capabilities
    w.write(b'{"return": {}, "id": 1}\n')
    await w.drain()
    await r.readline()                                  # "slow": reply late
    await asyncio.sleep(0.3)
    w.write(b'{"return": {}, "id": 2}\n')
    await w.drain()
    await r.readline()                                  # "next"
    w.write(b'{"return": "ok", "id": 3}\n')
    await w.drain()
    await asyncio.sleep(1)


def test_late_reply_after_timeout():
    async def run():
        path = Path(tempfile.mkdtemp(prefix="qmpt-")) / "q.sock"
        srv = await asyncio.start_unix_server(fake_qemu, str(path))
        q = QMP(lambda m: None)
        await q.connect(str(path), lambda: True)
        try:
            await q.cmd("slow", timeout=0.1)
            raise AssertionError("expected a timeout")
        except asyncio.TimeoutError:
            pass
        await asyncio.sleep(0.4)
        result = await q.cmd("next", timeout=1)
        srv.close()
        return result
    assert asyncio.run(run()) == "ok"
