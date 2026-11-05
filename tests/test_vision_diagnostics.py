"""Only known frame validation details may pass through the vision proxy."""
import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from backend.platform.routers import vision


class VisionDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, status, body):
        original = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
        with patch.dict('os.environ', {'VISION_SERVICE_URL':'https://vision.example','VISION_SERVICE_API_KEY':'private-test-key'}), \
             patch.object(vision.httpx, 'AsyncClient', side_effect=lambda **kwargs: original(transport=transport, **kwargs)):
            return await vision.forward('/v1/streams', 'POST', ('owner','site',{'auth_site_ms':123.4}))

    async def test_stale_frame_reason_and_stage_time(self):
        with self.assertRaises(HTTPException) as caught:
            await self.call(422, {'detail':'stale/future browser frame; observed_age_seconds=2.768; limit=2; synchronize clocks'})
        self.assertEqual(caught.exception.status_code, 422)
        self.assertIn('2.768s', caught.exception.detail)
        self.assertIn('123.4ms', caught.exception.detail)

    async def test_arbitrary_error_body_is_not_exposed(self):
        with self.assertRaises(HTTPException) as caught:
            await self.call(422, {'detail':'private-test-key remote traceback'})
        self.assertNotIn('private-test-key', caught.exception.detail)

    async def test_success_has_measured_proxy_timings(self):
        data = await self.call(200, {'analysis':None})
        self.assertEqual(data['proxy_timing']['auth_site_ms'],123.4)
        self.assertGreaterEqual(data['proxy_timing']['tracking_roundtrip_ms'],0)
