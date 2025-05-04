import queue
from typing import Tuple, Optional
import logging
import os
import re
import threading
import time
from irc.bot import SingleServerIRCBot
from logging.handlers import TimedRotatingFileHandler
import DCMS

# 机器人配置
IRC_CONFIG = {
    "server": "irc.freenode.net",
    "port": 6667,
    "nickname": "ircdcms_bridge",
    "channel": "#dcms"
}


def setup_logging() -> None:
    """配置日志系统，包括文件和控制台输出"""
    os.makedirs("log", exist_ok=True)
    log_handler = TimedRotatingFileHandler(
        filename="log/irc_bot.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8"
    )
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    
    for handler in (log_handler, console_handler):
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)
    
    logging.getLogger().setLevel(logging.INFO)

class MyIRCBot(SingleServerIRCBot):
    """
    IRC 机器人实现，用于在 IRC 和 DCMS 之间转发消息。
    
    负责处理 IRC 事件并与 DCMS 系统交互，实现消息的双向转发。
    """
    def __init__(self, server, port, nickname, channel, dcms: DCMS):
        super().__init__([(server, port)], nickname, nickname)
        self.channel = channel
        self.dcms = dcms
        self.nickname = nickname
        self.message_queue = queue.Queue()
        self.connected = False

    def on_welcome(self, connection, event):
        logging.info(f"Connected to {self.connection.server}")
        self.connected = True
        connection.join(self.channel)

        # 补发之前未成功发送的消息
        while not self.message_queue.empty():
            msg = self.message_queue.get()
            try:
                self.connection.privmsg(self.channel, msg)
                logging.info(f"[IRC - resend] {msg}")
            except Exception as e:
                logging.warning(f"Failed to resend message: {msg}, {e}")
                self.message_queue.put(msg)
                break  # 连接可能又失效了，停止重发

    def on_join(self, connection, event):
        nick = event.source.nick  # 获取加入者的昵称
        logging.info(f"{nick} joined channel {self.channel}")

    def on_pubmsg(self, connection, event):
        message = event.arguments[0]
        nick = event.source.nick

        # 不转发以分号和感叹号开头的消息
        if message.startswith(';') or message.startswith('!'):
            if message.startswith("!ircdcms"):  # 只处理自己的命令
                cmd = message[8:].strip()
                if cmd == "status":
                    self.connection.privmsg(self.channel, ";IRCDCMSBot: Connected to DCMS bridge")
                logging.info(f"[IRC] {nick}: {message}")
            return

        if nick.startswith("qqirc_bridge"):

            if message.startswith("[QQ]"):
                msg = message.split(":", 1)[1].strip()
                # 不转发QQ的命令消息
                if msg.startswith('!') or msg.startswith(';'):
                    logging.info(f"{message}")
                else:
                    logging.info(f"{message}")
                    self.dcms.post_message_room(message)
            else:
                logging.info(f"[QQ-IRCBOT] {message}")
        elif nick.startswith("ircxmpp_bridge"):
            if message.startswith("[XMPP]"):
                msg = message.split(":", 1)[1].strip()
                # 不转发XMPP的命令消息
                if msg.startswith('!') or msg.startswith(';'):
                    logging.info(f"{message}")
                else:
                    logging.info(f"{message}")
                    self.dcms.post_message_room(message)
        else:
            if message.startswith("!") or message.startswith("?"):
                logging.info(f"[IRC] {nick}: {message}")
            else:
                logging.info(f"[IRC] {nick}: {message}")
                self.dcms.post_message_room(message,"IRC",nick)

    def send_message_to_irc(self, message):
        if self.connected:
            try:
                self.connection.privmsg(self.channel, message)
            except Exception as e:
                logging.warning(f"Send failed, queuing: {message}")
                self.connected = False
                self.message_queue.put(message)
        else:
            logging.info(f"[Queueing] IRC not connected. Queued: {message}")
            self.message_queue.put(message)

    def on_disconnect(self, connection, event):
        logging.warning("Disconnected from server.")
        self.connected = False
        self.connection.connect(server=self.connection.server, port=self.connection.port, nickname=self.nickname)
        logging.info(f"Connected to {self.connection.server}")
        self.connected = True
        connection.join(self.channel)

    def on_kick(self, connection, event):
        target = event.arguments[0]
        if target == self.connection.get_nickname():
            logging.warning("Bot was kicked from the channel. Rejoining in 10 seconds...")
            connection.join(self.channel)
            logging.info(f"Connected to {self.connection.server} {self.channel}")
            self.connected = True


def poll_api_forever(dcms, irc_bot: MyIRCBot):
    while True:
        try:
            result = dcms.get_new_messages_from_room()
            # Compare
            if result is not None:
                for message in result:
                    #print(message['id_user'])
                    nick = dcms.get_user_nickname(message['id_user'])
                    #print(nick)
                    #print(dcms.username)
                    if nick != dcms.username:

                        logging.info("[DCMS] "+nick+": "+re.sub(r'[\r\n]+', ' ', message['msg']))
                        irc_bot.send_message_to_irc("[DCMS] "+nick+": "+re.sub(r'[\r\n]+', ' ', message['msg']))
        except TimeoutError as e:
            logging.error("[DCMSAPI] Timeout error.")
        except Exception as e:
            logging.error(f"[API Polling Error] {e}")
        time.sleep(5)

def run_bot_forever():

    dcms = DCMS.DCMS("dcmsirc_bot", "password")
    dcms.login()
    #logging.info(dcms.load_cookies())

    while True:
        try:
            logging.info("Starting IRC bot...")
            bot = MyIRCBot(IRC_CONFIG["server"], IRC_CONFIG["port"], IRC_CONFIG["nickname"], IRC_CONFIG["channel"], dcms)


            api_polling_thread = threading.Thread(target=poll_api_forever, args=(dcms, bot))
            api_polling_thread.daemon = True  # 设置为守护线程，程序退出时自动结束
            api_polling_thread.start()

            bot.start()
        except Exception as e:
            logging.error(f"Bot crashed: {e}. Retrying in 15 seconds...", exc_info=True)
            time.sleep(15)

if __name__ == "__main__":
    setup_logging()
    run_bot_forever()
