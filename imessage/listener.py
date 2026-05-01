"""imessage listener daemon.

reads from chat.db (read-only), polls for new messages addressed to ro,
forwards to the supervisor, writes the reply back via applescript.

phase 4 hooks this up. this scaffold runs but is a no-op until phase 4
flips the polling and applescript pieces on.
"""

from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger("ro.imessage")


async def main() -> None:
    log.info("imessage listener started, idle until phase 4")
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
