import nonebot
from nonebot import on_message
from nonebot.adapters.onebot.v11 import Adapter, GroupMessageEvent
from nonebot.adapters import Message
from nonebot.rule import is_type
import asyncio
import os
import pydle
import emojiswitch
import _thread
import time 

# 全局变量
is_transmessage = True
channel = '#dcms'
group_id = 310379632
bot_id = 3862850347
message_headers = ('[DCMS] ', '[WV] ', '[XMPP] ', '[TG]')
start_time = time.time()  # 启动时间

emoji_dict={4: '得意', 5: '流泪', 8: '睡', 9: '大哭', 10: '尴尬', 12: '调皮', 14: '微笑', 16: '酷', 21: '可爱', 23: '傲慢', 24: '饥饿', 25: '困', 26: '惊恐', 27: '流汗', 28: '憨笑', 29: '悠闲', 30: '奋斗', 32: '疑问', 33: '嘘', 34: '晕', 38: '敲打', 39: '再见', 41: '发抖', 42: '爱情', 43: '跳跳', 49: '拥抱', 53: '蛋糕', 60: '咖啡', 63: '玫瑰', 66: '爱心', 74: '太阳', 75: '月亮', 76: '赞', 78: '握手', 79: '胜利', 85: '飞吻', 89: '西瓜', 96: '冷汗', 97: '擦汗', 98: '抠鼻', 99: '鼓掌', 100: '糗大了', 101: '坏笑', 102: '左哼哼', 103: '右哼哼', 104: '哈欠', 106: '委屈', 109: '左亲亲', 111: '可怜', 116: '示爱', 118: '抱拳', 120: '拳头', 122: '爱你', 123: 'NO', 124: 'OK', 125: '转圈', 129: '挥手', 144: '喝彩', 147: '棒棒糖', 171: '茶', 173: '泪奔', 174: '无奈', 175: '卖萌', 176: '小纠结', 179: 'doge', 180: '惊喜', 181: '骚扰', 182: '笑哭', 183: '我最美', 201: '点赞', 203: '托脸', 212: '托腮', 214: '啵啵', 219: '蹭一蹭', 222: '抱抱', 227: '拍手', 232: '佛系', 240: '喷脸', 243: '甩头', 246: '加油抱抱', 262: '脑阔疼', 264: '捂脸', 265: '辣眼睛', 266: '哦哟', 267: '头秃', 268: '问号脸', 269: '暗中观察', 270: 'emm', 271: '吃瓜', 272: '呵呵哒', 273: '我酸了', 277: '汪汪', 278: '汗', 281: '无眼笑', 282: '敬礼', 284: '面无表情', 285: '摸鱼', 287: '哦', 289: '睁眼', 290: '敲开心', 293: '摸锦鲤', 294: '期待', 297: '拜谢', 298: '元宝', 299: '牛啊', 305: '右亲亲', 306: '牛气冲天', 307: '喵喵', 314: '仔细分析', 315: '加油', 318: '崇拜', 319: '比心', 320: '庆祝', 322: '拒绝', 324: '吃糖', 326: '生气'}

# 初始化 NoneBot
nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(Adapter)

# IRC 客户端类
class MyOwnBot(pydle.Client):
    async def on_connect(self):
        await self.join(channel)

    async def on_message(self, target, source, message):
        global is_transmessage
        if source != self.nickname:  # 避免自我消息循环
            await self.handle_irc_message(source, message)

    async def handle_irc_message(self, source, message):
        try:
            if message == '!qqirc on':
                await self.toggle_transmessage(True)
            elif message == '!qqirc off':
                await self.toggle_transmessage(False)
            elif message == '!qqirc status':
                await self.report_status(source)
            elif is_transmessage and not message.startswith(';'):
                try:
                    qqbot = nonebot.get_bot()
                    message = emojiswitch.emojize(message, delimiters=(":", ":"), lang="en")
                    if message.startswith(message_headers):
                        await qqbot.send_group_msg(group_id=group_id, message=f'{message}')
                    else:
                        await qqbot.send_group_msg(group_id=group_id, message=f'[IRC] {source}: {message}')
                except Exception as e:
                    print(f"Failed to send group message: {e}")
        except:
            self.restart_script()

    async def report_status(self, source):
        uptime = time.time() - start_time
        uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime))
        try:
            qq_logged_in = "Yes" if nonebot.get_bot() else "No"
        except:
            qq_logged_in = "No"
        irc_logged_in = "Yes" if self.connected else "No"
        status_message = (
            f"Status Report:\n"
            f"QQ Bot ID: {bot_id}\n"
            f"Uptime: {uptime_str}\n"
            f"QQ Logged In: {qq_logged_in}\n"
            f"IRC Logged In: {irc_logged_in}"
        )
        try:
            await self.message(channel, status_message)
        except Exception as e:
            print(f"Failed to send status message: {e}")

    async def toggle_transmessage(self, state):
        global is_transmessage
        is_transmessage = state
        status = "Enabled" if state else "Disabled"
        try:
            await self.message(channel, status)
        except Exception as e:
            print(f"Failed to send toggle message: {e}")

    async def send_message(self, target, message):
        try:
            await self.message(target, message)
        except:
            self.restart_script()

    def restart_script(self):
        os.system(r'start C:\Users\x8192Bit\Documents\qq-irc\run.bat')
        exit()

client = MyOwnBot('qqirc_bridge', realname='qqirc_bridge')

# 加载插件
nonebot.load_plugins("qq-irc/plugins")

# QQ 消息事件处理
groupMessageEvent = on_message(rule=is_type(GroupMessageEvent), priority=2)

@groupMessageEvent.handle()
async def handleGroupMessage(event: nonebot.adapters.Event):
    global is_transmessage
    if f'group_{group_id}' in event.get_session_id():
        await process_group_message(event)

async def process_group_message(event):
    global is_transmessage
    qqbot = nonebot.get_bot()
    message_text = event.get_message().extract_plain_text()

    commands = {
        '!qqirc on': lambda: set_transmessage_state(qqbot, True),
        '!qqirc off': lambda: set_transmessage_state(qqbot, False)
    }

    if message_text in commands:
        status = "Enabled" if message_text == 'qqirc on' else "Disabled"
        await commands[message_text]()
        await qqbot.send_group_msg(group_id, f"Transmessage state: {status}")
    elif not message_text.startswith(';'):
        await forward_group_message_to_irc(event)

async def set_transmessage_state(qqbot, state):
    global is_transmessage
    is_transmessage = state

async def forward_group_message_to_irc(event):
    nickname = event.sender.card or event.sender.nickname
    nickname = emojiswitch.demojize(str(nickname), delimiters=(":", ":"), lang="zh")

    # 合并消息段
    combined_message = []
    for message_segment in event.get_message():
        segment_text = await process_message_segment(message_segment)
        if segment_text:
            combined_message.append(segment_text)

    # 分号开头之消息，不转发
    if combined_message and not combined_message[0].startswith(';'):
        # 解决该死的一堆表情的问题
        await client.send_message(channel, f'[QQ] {nickname}: {" ".join(combined_message)}')

async def process_message_segment(message_segment):
    handlers = {
        'text': lambda: emojiswitch.demojize(message_segment.to_rich_text(), delimiters=(":", ":"), lang="zh"),
        'image': lambda: f'[图片] {message_segment.data["url"]}',
        'face': lambda: f'[表情] {emoji_dict[int(message_segment.data["id"])] if int(message_segment.data["id"]) in emoji_dict else message_segment.data["id"]}',
        'record': lambda: f'[语音] {message_segment.data["file"]}',
        'video': lambda: f'[视频] {message_segment.data["file"]}',
        'at': lambda: f'@{message_segment.data["qq"]}',
        'rps': lambda: '[猜拳]',
        'dice': lambda: '[骰子]',
        'shake': lambda: '[窗口抖动]',
        'poke': lambda: '[戳一戳]',
        'reply': lambda: '[回复]',
        'share': lambda: f'[链接标题] {message_segment.data["title"]} [链接内容] {message_segment.data["url"]}'
    }

    handler = handlers.get(message_segment.type)
    return handler() if handler else None

# 启动 IRC 客户端
def runIRCClient():
    client.run('chat.freenode.net')

_thread.start_new_thread(runIRCClient, ())
nonebot.run()