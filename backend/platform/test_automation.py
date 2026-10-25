"""One bounded server-side random command run, independent of open browser tabs."""
import asyncio
import random
import time

from . import config
from .database import SessionLocal
from .routers import test_control, test_push


def random_command(state):
    if state['estop']:
        return 'CLEAR_ESTOP'
    return random.choice({
        'IDLE': ['DISPATCH'], 'DISPATCHED': ['ESTOP', 'CANCEL', 'DEPLOY', 'RETURN'],
        'DEPLOYING': ['COMPLETE', 'ESTOP'], 'RETURNING': ['COMPLETE', 'ESTOP'],
    }.get(state['status'], ['DISPATCH']))


class Automation:
    def __init__(self):
        self.task = None
        self.halt = None
        self.ends_at = 0
        self.generated = 0
        self.error = None

    def status(self):
        return dict(running=self.task is not None and not self.task.done(),
                    generated=self.generated, remaining_seconds=max(0, int(self.ends_at - time.monotonic())),
                    error=self.error, available=not config.IS_VERCEL)

    def start(self):
        if config.IS_VERCEL:
            from fastapi import HTTPException
            raise HTTPException(409, '자동 발생기는 상시 실행되는 로컬 서버가 필요합니다. Vercel에서는 수동 테스트만 가능합니다.')
        if self.task is None or self.task.done():
            self.halt = asyncio.Event()
            self.generated = 0
            self.error = None
            self.ends_at = time.monotonic() + 600
            self.task = asyncio.create_task(self.run())
        return self.status()

    async def stop(self):
        if self.halt is not None:
            self.halt.set()
        if self.task is not None:
            await self.task
        self.ends_at = 0
        return self.status()

    async def run(self):
        try:
            while not self.halt.is_set():
                remaining = self.ends_at - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(self.halt.wait(), timeout=min(random.uniform(5, 15), remaining))
                    break
                except asyncio.TimeoutError:
                    pass
                if time.monotonic() >= self.ends_at:
                    break
                with SessionLocal() as db:
                    state = test_control.current(db)
                    body = test_control.CommandInput(command=random_command(state),
                                                     target_x=round(random.uniform(1, 20), 1),
                                                     target_y=round(random.uniform(1, 20), 1))
                    packet = test_control.send(body, db)
                self.generated += 1
                await asyncio.to_thread(test_push.deliver, packet)
        except Exception:
            self.error = '자동 발생 중 오류가 발생했습니다. 서버 로그와 DB 연결을 확인한 뒤 재시작하세요.'
            import logging
            logging.getLogger(__name__).exception('Automatic test commands stopped')


automation = Automation()
