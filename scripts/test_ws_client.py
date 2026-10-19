#!/usr/bin/env python3
"""Simple test client that connects to backend websocket endpoint and prints messages.
Run inside the backend container so it connects to ws://localhost:8000/ws
"""
import asyncio
import json
import os
import websockets

async def run():
    uri = 'ws://localhost:8000/ws'
    print('connecting to', uri)
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({'type': 'auth', 'token': os.environ['WS_ACCESS_TOKEN']}))
            print('connected')
            # receive messages for 20 seconds
            async def recv():
                try:
                    while True:
                        msg = await ws.recv()
                        print('recv:', msg)
                except Exception as e:
                    print('recv loop finished', e)

            r = asyncio.create_task(recv())
            await asyncio.sleep(20)
            r.cancel()
    except Exception as e:
        print('connection failed', e)

if __name__ == '__main__':
    if not os.getenv('WS_ACCESS_TOKEN'):
        raise SystemExit('请先设置 WS_ACCESS_TOKEN 为当前用户的访问令牌')
    asyncio.run(run())
