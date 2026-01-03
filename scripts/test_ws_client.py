#!/usr/bin/env python3
"""Simple test client that connects to backend websocket endpoint and prints messages.
Run inside the backend container so it connects to ws://localhost:8000/ws
"""
import asyncio
import websockets

async def run():
    uri = 'ws://localhost:8000/ws'
    print('connecting to', uri)
    try:
        async with websockets.connect(uri) as ws:
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
    asyncio.run(run())
