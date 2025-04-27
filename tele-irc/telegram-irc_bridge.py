import threading
import time
import datetime
import irc.client
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# 状态控制变量
relay_enabled = threading.Event()
relay_enabled.set()
start_time = datetime.datetime.now()

# IRC 设置
IRC_SERVER = "chat.freenode.net"
IRC_PORT = 6667
IRC_NICK = "irctele_bridge"
IRC_CHANNEL = "#dcms"

# Telegram 设置
TELEGRAM_TOKEN = "8194432969:AAEeAWXT0GB97pz0K9lnyhYnBBcJHJyrdpo" # Hidden
TELEGRAM_CHAT_ID = "-100xxxxxxxxxx"  # Pending
class TelegramBot:
    def __init__(self, token, chat_id, irc_send_callback=None):
        self.token = token
        self.chat_id = chat_id
        self.bot = Bot(token=token)
        self.app = Application.builder().token(token).build()
        self.irc_send_callback = irc_send_callback
        self.bot_username = None

    async def send_message(self, message: str) -> None:
        await self.bot.send_message(chat_id=self.chat_id, text=message)

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.message.from_user.username or update.message.from_user.first_name
        body = update.message.text

        if user == self.bot_username:
            return

        if body:
            # 处理命令
            if body.startswith('!irctele'):
                cmd = body[8:].strip()
                if cmd == "on":
                    relay_enabled.set()
                    await self.send_message(";Relay enabled")
                elif cmd == "off":
                    relay_enabled.clear()
                    await self.send_message(";Relay disabled")
                elif cmd == "status":
                    status = "enabled" if relay_enabled.is_set() else "disabled"
                    uptime = datetime.datetime.now() - start_time
                    irc_status = "unknown"
                    if self.irc_send_callback and hasattr(self.irc_send_callback, '__self__'):
                        irc_bot = self.irc_send_callback.__self__
                        if hasattr(irc_bot, 'connection'):
                            irc_status = "connected" if irc_bot.connection.is_connected() else "disconnected"
                    await self.send_message(
                        f";Status: {status} | Online: {str(uptime).split('.')[0]} | IRC: {irc_status} | Telegram: connected"
                    )
                return

            # 普通消息
            if body.startswith(';') or body.startswith('!'):
                return  # 保护

            if relay_enabled.is_set():
                formatted = f"[Telegram] {user}: {body}"
                print(f"Received from Telegram: {formatted}")
                if self.irc_send_callback:
                    self.irc_send_callback(formatted)

    async def start(self):
        me = await self.bot.get_me()
        self.bot_username = me.username
        
        # 设置消息处理器
        self.app.add_handler(MessageHandler(
            filters.TEXT & filters.Chat(chat_id=int(self.chat_id)), 
            self.on_message
        ))
        
        # 启动机器人
        await self.app.initialize()
        await self.app.start()
        await self.app.running()
        
        print(f"Telegram bot started as @{self.bot_username}")

    async def stop(self):
        await self.app.stop()

class IRCBot:
    def __init__(self, server, port, nickname, channel, telegram_bot):
        self.server = server
        self.port = port
        self.nickname = nickname
        self.channel = channel
        self.telegram_bot = telegram_bot
        self.reactor = irc.client.Reactor()
        self.connection = self.reactor.server().connect(server, port, nickname)
        self.connection.add_global_handler("welcome", self.on_connect)
        self.connection.add_global_handler("pubmsg", self.on_pubmsg)

    def on_connect(self, connection, event):
        connection.join(self.channel)
        print(f"Joined IRC channel {self.channel}")

    def on_pubmsg(self, connection, event):
        message = event.arguments[0]
        sender = event.source.nick

        if message.startswith(';') or message.startswith('!'):
            return

        formatted = f"[IRC] {sender}: {message}"
        if relay_enabled.is_set():
            self.telegram_bot.send_message(formatted)

    def send_to_irc(self, message: str) -> None:
        self.connection.privmsg(self.channel, message)

    def start(self) -> None:
        self.reactor.process_forever()

def run_telegram_bot(telegram_bot: TelegramBot) -> None:
    import asyncio
    asyncio.run(telegram_bot.start())

def main() -> None:
    irc_bot = None

    def irc_send_callback(msg: str) -> None:
        if irc_bot:
            irc_bot.send_to_irc(msg)

    telegram_bot = TelegramBot(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, irc_send_callback=irc_send_callback)

    telegram_thread = threading.Thread(target=run_telegram_bot, args=(telegram_bot,))
    telegram_thread.daemon = True
    telegram_thread.start()

    time.sleep(2)

    nonlocal_irc_bot = {}
    irc_bot = IRCBot(IRC_SERVER, IRC_PORT, IRC_NICK, IRC_CHANNEL, telegram_bot)
    nonlocal_irc_bot['bot'] = irc_bot

    def irc_send_callback2(msg):
        nonlocal_irc_bot['bot'].send_to_irc(msg)
    telegram_bot.irc_send_callback = irc_send_callback2

    irc_bot.start()

if __name__ == "__main__":
    main()
