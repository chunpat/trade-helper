#!/usr/bin/env python3
"""Long-running websocket client for manual integration testing.
Connects to backend websocket endpoint and prints incoming messages.
"""
import asyncio
import websockets
import json
import os

URI = 'ws://localhost:8029/ws'

async def run():
    while True:
        try:
            print('Connecting to', URI)
            async with websockets.connect(URI, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(json.dumps({'type': 'auth', 'token': os.environ['WS_ACCESS_TOKEN']}))
                print('Connected')
                try:
                    async for msg in ws:
                        try:
                            payload = json.loads(msg)
                            print('MSG:', payload)
                        except Exception:
                            print('RAW:', msg)
                except Exception as e:
                    print('receive loop ended:', e)
        except Exception as e:
            print('connect failed:', e)
        print('Reconnecting in 3s...')
        await asyncio.sleep(3)

if __name__ == '__main__':
    if not os.getenv('WS_ACCESS_TOKEN'):
        raise SystemExit('请先设置 WS_ACCESS_TOKEN 为当前用户的访问令牌')
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print('exiting')
