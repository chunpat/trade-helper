#!/usr/bin/env python3
"""Synchronous websocket client using websocket-client package.
Connects to ws://localhost:8029/ws and prints messages for 60 seconds.
"""
import time
from websocket import WebSocketApp
import json
import os

URI = 'ws://localhost:8029/ws'

def on_open(ws):
    ws.send(json.dumps({'type': 'auth', 'token': os.environ['WS_ACCESS_TOKEN']}))
    print('open')

def on_message(ws, msg):
    try:
        print('MSG:', json.loads(msg))
    except Exception:
        print('RAW:', msg)

def on_close(ws, close_status_code, close_msg):
    print('closed', close_status_code, close_msg)

def on_error(ws, err):
    print('error', err)

if __name__ == '__main__':
    if not os.getenv('WS_ACCESS_TOKEN'):
        raise SystemExit('请先设置 WS_ACCESS_TOKEN 为当前用户的访问令牌')
    ws = WebSocketApp(URI, on_open=on_open, on_message=on_message, on_close=on_close, on_error=on_error)
    # run for a period
    import threading
    t = threading.Thread(target=ws.run_forever)
    t.daemon = True
    t.start()
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        pass
    ws.close()
    t.join()
    print('done')
