import os
import time
import pygame
import asyncio
import edge_tts
import requests
from io import BytesIO
from dotenv import load_dotenv
from bilibili_api import live

voice = 'zh-CN-XiaoxiaoNeural'
load_dotenv()
pygame.mixer.init()
ts = int(time.time() * 1000)
semaphore = asyncio.Semaphore(1)
danmaku_queue = asyncio.Queue(maxsize=10)
text_queue = asyncio.Queue(maxsize=10)
sound_queue = asyncio.Queue(maxsize=10)
room = live.LiveDanmaku(room_display_id=int(os.getenv('room')))


@room.on('DANMU_MSG')
async def on_danmaku(event):
    info_list = event.get('data', {}).get('info', [])
    if info_list:
        name = info_list[2][1]
        danmaku = info_list[1]
        print('[弹幕]{}-{}'.format(name, danmaku))
        if danmaku.startswith('Q:'):
            danmaku = danmaku[2:].strip()
        if not danmaku_queue.full() and len(danmaku) > 0:
            await danmaku_queue.put(danmaku)


@room.on('SEND_GIFT')
async def on_gift(event):
    data = event.get('data', {}).get('data', {})
    if data:
        print('[礼物]{}-{}-{}'.format(data.get('uname'), data.get('action'), data.get('giftName')))


async def get_sound(text):
    print('get_sound')
    sound = b''
    try:
        communicate = edge_tts.Communicate(text, voice)
        async for chunk in communicate.stream():
            if chunk['type'] == 'audio':
                sound += chunk['data']
    except Exception as e:
        print(e)
    finally:
        print('get_sound_done')
        return sound


async def play_sound(sound):
    print('play_sound')
    file = BytesIO(sound)
    music = pygame.mixer.Sound(file)
    async with semaphore:
        music.play()
        pygame.time.wait(int(music.get_length() * 1000))
        print('play_sound_done')


async def get_chatgpt(prompt, id):
    url = 'https://api.binjie.fun/api/generateStream'
    data = {
        'prompt': prompt,
        'userId': '#/chat/{}'.format(id),
        'network': False,
        'system': '',
        'withoutContext': False,
        'stream': False
    }
    headers = {
        'origin': 'https://chat.jinshutuan.com',
        'referer': 'https://chat.jinshutuan.com/'
    }
    try:
        resp = requests.get(url=url, data=data, headers=headers)
        print('[GPT]{}'.format(resp.text))
        return resp.text
    except Exception as e:
        print(e)


async def handle_danmaku_queue():
    prompt = '你是一个虚拟主播，现在正在进行直播。观众将向你进行提问，你需要回答这些问题。你的回答长度必须小于50个字符。'
    await get_chatgpt(prompt, ts)
    while True:
        if not danmaku_queue.empty():
            danmaku = await danmaku_queue.get()
            text = await get_chatgpt(danmaku, ts)
            await text_queue.put(text)
        await asyncio.sleep(0.1)


async def handle_text_queue():
    while True:
        if not text_queue.empty():
            text = await text_queue.get()
            sound = await get_sound(text)
            await sound_queue.put(sound)
        await asyncio.sleep(0.1)


async def handle_sound_queue():
    while True:
        if not sound_queue.empty():
            sound = await sound_queue.get()
            await play_sound(sound)
        await asyncio.sleep(0.1)


async def main():
    await asyncio.gather(room.connect(), handle_danmaku_queue(), handle_text_queue(), handle_sound_queue())


if __name__ == '__main__':
    loop = asyncio.get_event_loop_policy().get_event_loop()
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
