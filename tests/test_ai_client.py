"""AI gateway contract and credential isolation; no external requests."""
import os
import unittest
from unittest.mock import patch

import httpx

from backend.platform import ai_client


class AIClientTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, handler):
        original = httpx.AsyncClient
        with patch.dict(os.environ, {'DG_AI_KEY': 'test-private-key', 'DG_AI_URL': ''}), \
             patch.object(ai_client.httpx, 'AsyncClient',
                          side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs)):
            return await ai_client.detect(b'image-bytes', 'frame.jpg', 'image/jpeg', 7)

    async def test_default_modal_endpoint_and_multipart_auth(self):
        result = {'image_size': [640, 480], 'detections': [], 'frame_id': '7'}

        def handler(request):
            self.assertEqual(str(request.url), ai_client.DEFAULT_AI_URL + '/detect')
            self.assertEqual(request.headers['Authorization'], 'Bearer test-private-key')
            self.assertIn('multipart/form-data', request.headers['Content-Type'])
            self.assertIn(b'name="image"', request.content)
            self.assertIn(b'name="frame_id"', request.content)
            return httpx.Response(200, json=result)

        self.assertEqual(await self.request(handler), result)

    async def test_remote_error_body_never_reaches_browser(self):
        with self.assertRaises(ai_client.AIClientError) as caught:
            await self.request(lambda request: httpx.Response(500, text='test-private-key internal traceback'))
        self.assertNotIn('test-private-key', str(caught.exception))
        self.assertIn('500', str(caught.exception))

    async def test_invalid_key(self):
        with self.assertRaisesRegex(ai_client.AIClientError, '인증 실패'):
            await self.request(lambda request: httpx.Response(401))

    async def test_missing_key_fails_before_network(self):
        with patch.dict(os.environ, {'DG_AI_KEY': ''}):
            with self.assertRaisesRegex(ai_client.AIClientError, 'DG_AI_KEY'):
                await ai_client.detect(b'image', 'frame.jpg', 'image/jpeg')
