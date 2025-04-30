import logging
import threading
import time
import datetime
import irc.client
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes,
)

# 日志配置 
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
logging.getLogger('telegram').setLevel(logging.DEBUG)
logging.getLogger('telegram.ext').setLevel(logging.DEBUG)
logging.getLogger('irc').setLevel(logging.DEBUG)

# 状态控制
relay_enabled = threading.Event()
relay_enabled.set()
start_time = datetime.datetime.now()

# IRC 配置
IRC_SERVER  = "chat.freenode.net"
IRC_PORT    = 6667
IRC_NICK    = "irctele_bridge"
IRC_CHANNEL = "#dcms"

#Telegram 配置
TELEGRAM_TOKEN   = "Hide"
TELEGRAM_CHAT_ID = -1

class TelegramBot:
    def __init__(self, token: str, chat_id: int):
        self.chat_id = chat_id
        self.app = ApplicationBuilder().token(token).http_version("1.1").connection_pool_size(100).build()
        self.bot_username = None
        self.irc_send_callback = None
        self.loop = None  # 用于存储轮询线程的事件循环

        # 注册消息处理器（调试阶段不加 filters.Chat）
        self.app.add_handler(
            MessageHandler(filters.TEXT, self.handle_message)
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user.username or update.effective_user.first_name
        text = update.message.text or ""

        # 第一次消息时获取 Bot 用户名
        if not self.bot_username:
            me = await context.bot.get_me()
            self.bot_username = me.username

        logging.debug(f"Telegram 收到消息：chat.id={chat.id}, type={chat.type}, text={text}")

        # 忽略自身或空消息
        if not text or user == self.bot_username:
            return

        # 控制指令
        if text.startswith('!irctele'):
            cmd = text[len('!irctele'):].strip().lower()
            if cmd == "on":
                relay_enabled.set()
                await context.bot.send_message(self.chat_id, "；已开启消息中继")
            elif cmd == "off":
                relay_enabled.clear()
                await context.bot.send_message(self.chat_id, "；已关闭消息中继")
            elif cmd == "status":
                status = "开启" if relay_enabled.is_set() else "关闭"
                uptime = datetime.datetime.now() - start_time
                await context.bot.send_message(
                    self.chat_id,
                    f"；状态：{status} | 已运行：{str(uptime).split('.')[0]}"
                )
            return

        # 忽略其他机器人命令
        if text.startswith(('!',';')):
            return

        # 转发到 IRC
        if relay_enabled.is_set() and self.irc_send_callback:
            msg = f"[TG] {user}: {text}"
            logging.debug(f"调度转发到 IRC: {msg}")
            self.irc_send_callback(msg)

    def run(self):
        """在独立线程中创建并绑定事件循环，然后同步启动轮询"""
        logging.debug("TelegramBot.run()：创建新事件循环并绑定到当前线程")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        logging.debug("TelegramBot.run()：开始 run_polling()")
        self.app.run_polling()

class IRCBot:
    def __init__(self, server, port, nickname, channel, telegram_bot: TelegramBot):
        self.relay_bot = telegram_bot
        self.reactor = irc.client.Reactor()
        self.conn = self.reactor.server().connect(server, port, nickname)
        self.conn.add_global_handler("welcome", self.on_connect)
        self.conn.add_global_handler("pubmsg", self.on_pubmsg)

    def on_connect(self, connection, event):
        logging.debug(f"IRCBot: 已连接 IRC 服务器，加入频道 {IRC_CHANNEL}")
        connection.join(IRC_CHANNEL)

    def on_pubmsg(self, connection, event):
        text = event.arguments[0]
        user = event.source.nick
        logging.debug(f"IRCBot 收到消息：{user}: {text}")

        # 去掉 [IRC] 前缀，避免嵌套
        if text.startswith("[IRC]"):
            text = text[len("[IRC]"):].strip()

        # 转发到 Telegram
        if relay_enabled.is_set() and not text.startswith(('!', ';')):
            msg = f"[IRC] {user}: {text}"
            if "[QQ]" in text:  # 如果消息中包含 [QQ]，只保留 [QQ] 开头的部分
                msg = text[text.index("[QQ]"):]
            if "[XMPP]" in text:
                msg = text[text.index("[XMPP]"):]
            if "[DCMS]" in text:
                msg = text[text.index("[DCMS]"):]
            logging.debug(f"调度转发到 Telegram: {msg}")
            asyncio.run_coroutine_threadsafe(
                self.relay_bot.app.bot.send_message(self.relay_bot.chat_id, msg),
                self.relay_bot.loop
            )

    def send_to_irc(self, message: str):
        def _send():
            self.conn.privmsg(IRC_CHANNEL, message)
        logging.debug(f"调度发送到 IRC 频道: {message}")
        self.reactor.scheduler.execute_after(0, _send)

    def start(self):
        logging.debug("IRCBot: 启动 Reactor 事件循环")
        self.reactor.process_forever()


def main():
    logging.debug("主程序启动")
    # 1) 启动 Telegram 轮询线程
    tg_bot = TelegramBot(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    t = threading.Thread(target=tg_bot.run, daemon=True, name="TG-Thread")
    t.start()
    time.sleep(1)
    logging.debug(f"TG-Thread alive? {t.is_alive()}")

    # 2) 启动 IRC Bot
    irc_bot = IRCBot(IRC_SERVER, IRC_PORT, IRC_NICK, IRC_CHANNEL, tg_bot)
    tg_bot.irc_send_callback = irc_bot.send_to_irc
    # 可以用线程，也可以直接阻塞调用 start()
    i = threading.Thread(target=irc_bot.start, daemon=True, name="IRC-Thread")
    i.start()
    time.sleep(1)
    logging.debug(f"IRC-Thread alive? {i.is_alive()}")

    # 主线程保持活跃，防止脚本提前退出
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        logging.debug("主程序收到中断，正在退出...")

if __name__ == "__main__":
    main()
