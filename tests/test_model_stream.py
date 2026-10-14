"""Transport tests without a camera, OpenCV, or model weights."""
import http.client
import threading
import unittest

from scripts.model_stream import LatestFrame, make_server


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.frames = LatestFrame()
        self.server = make_server('127.0.0.1', 0, self.frames, 'test-stream-key', 'https://dashboard.test')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connections = []

    def tearDown(self):
        self.frames.close()
        for connection in self.connections:
            connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path='/stream', method='GET', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)
        self.connections.append(connection)
        connection.request(method, path, headers=headers or {})
        return connection.getresponse()

    def test_auth_and_origin(self):
        self.assertEqual(self.request().status, 401)
        self.assertEqual(self.request(headers={'Authorization': 'Bearer wrong'}).status, 401)
        self.assertEqual(self.request(headers={'Origin': 'https://other.test'}).status, 403)
        response = self.request(method='OPTIONS', headers={'Origin': 'https://dashboard.test'})
        self.assertEqual(response.status, 204)
        self.assertEqual(response.getheader('Access-Control-Allow-Headers'), 'Authorization')

    def test_stream_uses_latest_annotated_jpeg(self):
        self.frames.publish(b'old-frame')
        jpeg = b'\xff\xd8annotated-frame\xff\xd9'
        self.frames.publish(jpeg)
        response = self.request(headers={'Authorization': 'Bearer test-stream-key'})
        expected = (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
                    str(len(jpeg)).encode() + b'\r\n\r\n' + jpeg + b'\r\n')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.read(len(expected)), expected)
        self.frames.close()
        self.assertEqual(response.read(), b'--frame--\r\n')

    def test_stale_frames_are_not_replayed(self):
        self.frames.publish(b'jpeg')
        self.frames.updated -= 20
        response = self.request('/health', headers={'Authorization': 'Bearer test-stream-key'})
        self.assertEqual(response.status, 503)
        self.assertIsNone(self.frames.next(0, timeout=0.01))


if __name__ == '__main__':
    unittest.main()
