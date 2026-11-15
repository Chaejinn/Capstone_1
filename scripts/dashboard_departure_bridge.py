"""Deployed dashboard AI -> bounded USB departure. Never reads test-control."""
import getpass
import threading
import time
from uuid import uuid4

import requests
import serial

BASE = 'https://drown-guardian.vercel.app/api'
SITE = 'chunjeon'


class Departure:
    def __init__(self, board):
        self.board = board
        self.lock = threading.Lock()
        self.until = 0
        self.failure = None

    def send(self, line):
        self.board.write((line + '\n').encode('ascii'))
        self.board.flush()

    def stop(self):
        with self.lock:
            self.until = 0
            self.send('S')

    def start(self, packet):
        # Client hard limits cannot be raised by remote packet values.
        remaining = min(3.0, float(packet['max_seconds']), float(packet['expires_at'])-time.time())
        if remaining <= 0 or packet.get('throttle') != 5:
            print('EXPIRED_OR_INVALID_DEPARTURE; skipped.', flush=True)
            return
        with self.lock:
            self.until = time.monotonic() + remaining
            self.send('M,5,0')
        print(f'DEPARTURE: throttle 5%, rudder 0, maximum {remaining:.2f}s', flush=True)

    def watchdog(self, shutdown):
        try:
            while not shutdown.wait(0.1):
                with self.lock:
                    if not self.until:
                        continue
                    if time.monotonic() >= self.until:
                        self.until = 0
                        self.send('S')
                        print('DEPARTURE LIMIT: STOP', flush=True)
                    else:
                        self.send('M,5,0')
        except serial.SerialException:
            self.failure = True
            shutdown.set()


def main():
    print('Dashboard departure: COM3 / 9600, site chunjeon. Ctrl+C stops.', flush=True)
    username = input('Web login ID: ').strip()
    password = getpass.getpass('Web password (hidden): ')
    http = requests.Session()
    board = departure = worker = None
    shutdown = threading.Event()
    bridge_id = str(uuid4())

    def api(path, body, timeout=(1, 1)):
        response = http.post(BASE+path, params={'site_id': SITE}, json=body,
                             timeout=timeout, allow_redirects=False)
        response.raise_for_status()
        return response.json()

    try:
        response = http.post(BASE+'/auth/login', data={'username':username,'password':password}, timeout=20)
        password = None
        print('LOGIN: HTTP '+str(response.status_code), flush=True)
        response.raise_for_status()
        http.headers['Authorization'] = 'Bearer '+response.json()['access_token']
        board = serial.Serial('COM3',9600,timeout=0.05,write_timeout=0.2)
        departure = Departure(board)
        time.sleep(4)
        board.reset_input_buffer()
        departure.stop()
        end = time.monotonic()+2
        while time.monotonic()<end:
            reply=board.readline().decode('ascii',errors='replace').strip()
            if reply: print('BOARD: '+reply,flush=True)
            if reply=='OK S': break
        else:
            raise RuntimeError('Initial stop not acknowledged')
        connected=api('/board-control/connect',{'bridge_id':bridge_id},timeout=(3,15))
        revision=connected['revision']
        worker=threading.Thread(target=departure.watchdog,args=(shutdown,),daemon=True)
        worker.start()
        print('ARMED: waiting for a NEW verified AI drowning confirmation. Test commands ignored.',flush=True)
        while not shutdown.is_set():
            packet=api('/board-control/poll',{'bridge_id':bridge_id})
            if packet['revision']>revision:
                revision=packet['revision']
                if packet['command']=='DISPATCH':
                    departure.start(packet)
                else:
                    departure.stop()
                    print('WEB STOP; restart bridge to re-arm.',flush=True)
                    break
            while board.in_waiting:
                reply=board.readline().decode('ascii',errors='replace').strip()
                if reply: print('BOARD: '+reply,flush=True)
            shutdown.wait(0.3)
        if departure.failure:
            print('SERIAL WATCHDOG FAILURE',flush=True)
    except KeyboardInterrupt:
        print('Stopping.',flush=True)
    except (requests.RequestException,serial.SerialException,ValueError,KeyError,RuntimeError):
        print('AUTH/NETWORK/SERIAL ERROR: stopping. Restart locally to re-arm.',flush=True)
    finally:
        shutdown.set()
        if worker: worker.join(timeout=2)
        try:
            if departure:
                departure.stop()
                end=time.monotonic()+1
                while time.monotonic()<end:
                    reply=board.readline().decode('ascii',errors='replace').strip()
                    if reply: print('BOARD: '+reply,flush=True)
                    if reply=='OK S': break
        except serial.SerialException:
            print('STOP NOT CONFIRMED: check board physically.',flush=True)
        finally:
            if board: board.close()
            http.close()


if __name__=='__main__':
    main()
