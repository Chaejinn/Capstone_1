"""Serve Detective-model's annotated display frames without opening another camera."""
from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class LatestFrame:
    def __init__(self):
        self.condition = threading.Condition()
        self.jpeg = None
        self.sequence = 0
        self.updated = 0.0
        self.closed = False

    def publish(self, jpeg):
        with self.condition:
            self.jpeg = bytes(jpeg)
            self.sequence += 1
            self.updated = time.monotonic()
            self.condition.notify_all()

    def next(self, sequence, timeout=10):
        with self.condition:
            self.condition.wait_for(lambda: self.sequence > sequence or self.closed, timeout)
            if self.closed or self.sequence <= sequence or time.monotonic() - self.updated > timeout:
                return None
            return self.sequence, self.jpeg

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()


def make_server(host, port, frames, token, origin):
    if not token or not origin:
        raise ValueError('A stream token and allowed dashboard origin are required.')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Do not record credentials or request URLs.

        def headers(self, status, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.end_headers()

        def allowed_origin(self):
            return self.headers_in_origin() in (None, origin)

        def headers_in_origin(self):
            return self.headers.get('Origin')

        def do_OPTIONS(self):
            if not self.allowed_origin():
                self.send_error(403)
                return
            self.send_response(204)
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Authorization')
            self.send_header('Vary', 'Origin')
            self.end_headers()

        def do_GET(self):
            if not self.allowed_origin():
                self.send_error(403)
                return
            if not hmac.compare_digest(self.headers.get('Authorization', ''), f'Bearer {token}'):
                self.respond(401, '영상 연결 키가 올바르지 않습니다.')
                return
            if self.path == '/health':
                ready = frames.next(0, timeout=0.1) is not None
                self.headers(200 if ready else 503, 'application/json')
                self.wfile.write(json.dumps({'ready': ready}).encode())
                return
            if self.path != '/stream':
                self.respond(404, '영상 경로를 찾을 수 없습니다.')
                return
            frame = frames.next(0)
            if frame is None:
                self.respond(503, 'AI 모델에서 영상을 수신하지 못했습니다.')
                return
            self.headers(200, 'multipart/x-mixed-replace; boundary=frame')
            try:
                while frame is not None:
                    sequence, jpeg = frame
                    self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
                                     str(len(jpeg)).encode() + b'\r\n\r\n' + jpeg + b'\r\n')
                    self.wfile.flush()
                    frame = frames.next(sequence)
                self.wfile.write(b'--frame--\r\n')
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

        def respond(self, status, detail):
            self.headers(status, 'application/json')
            self.wfile.write(json.dumps({'detail': detail}).encode())

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

    # Handler uses BaseHTTPRequestHandler.headers for request headers.
    Handler.send_response_headers = Handler.headers
    del Handler.headers
    Handler.headers = property(lambda self: self.__dict__['request_headers'],
                               lambda self, value: self.__dict__.__setitem__('request_headers', value))
    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', required=True, type=Path)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--origin', default='https://drown-guardian.vercel.app')
    parser.add_argument('--headless', action='store_true')
    args, model_args = parser.parse_known_args()
    token = os.environ.get('DG_MODEL_STREAM_TOKEN', '')
    if len(token) < 24:
        parser.error('Set DG_MODEL_STREAM_TOKEN to a random key of at least 24 characters.')
    model_dir = args.model_dir.resolve()
    if not (model_dir / 'src/inference/pipeline.py').is_file():
        parser.error('--model-dir must point to the Detective-model repository.')
    sys.path.insert(0, str(model_dir))
    import cv2
    from src.inference import pipeline

    frames = LatestFrame()
    server = make_server(args.host, args.port, frames, token, args.origin.rstrip('/'))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    original_show, original_wait, original_check = cv2.imshow, cv2.waitKey, pipeline._ensure_highgui

    def show(name, frame):
        ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            frames.publish(encoded.tobytes())
        if not args.headless:
            original_show(name, frame)

    cv2.imshow = show
    if args.headless:
        cv2.waitKey = lambda _delay: -1
        pipeline._ensure_highgui = lambda: None
    original_args = sys.argv
    sys.argv = [str(model_dir / 'main.py'), *model_args]
    print(f'AI video server: http://{args.host}:{args.port}/stream', flush=True)
    try:
        pipeline.main()
    finally:
        frames.close()
        server.shutdown()
        server.server_close()
        cv2.imshow, cv2.waitKey = original_show, original_wait
        pipeline._ensure_highgui = original_check
        sys.argv = original_args


if __name__ == '__main__':
    main()
