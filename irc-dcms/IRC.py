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

    def on_welcome(self, connection, event):
        logging.info(f"Connected to {self.connection.server}")
        connection.join(self.channel)

    def on_join(self, connection, event):
        nick = event.source.nick  # 获取加入者的昵称
        logging.info(f"{nick} joined channel {self.channel}")

    def on_pubmsg(self, connection, event):
        message = event.arguments[0]
        nick = event.source.nick

        if nick == "qqirc_bridge":

            if message.startswith("[QQ]"):
                msg = message.split(":", 1)[1].strip()
                if msg.startswith("!") or msg.startswith("?"):
                    logging.info(f"{message}")
                else:
                    logging.info(f"{message}")
                    self.dcms.post_message_room(message)
            else:
                logging.info(f"[QQ-IRCBOT] {message}")
        elif nick == "ircxmpp_bridge":
            if message.startswith("[XMPP]"):
                msg = message.split(":", 1)[1].strip()
                if msg.startswith("!") or msg.startswith("?"):
                    logging.info(f"{message}")
                else:
                    logging.info(f"{message}")
                    self.dcms.post_message_room(message)
        else:
            if message.startswith("!") or message.startswith("?"):
                logging.info(f"[IRC] {nick}: {message}")
            else:
                logging.info(f"[IRC] {nick}: {message}")
                self.dcms.post_message_room("IRC", nick, message)

    def send_message_to_irc(self, message):
        self.connection.privmsg(self.channel, message)

    def on_disconnect(self, connection, event):
        logging.warning("Disconnected from server.")
        # 移除了异常抛出，让外部循环处理重连

    def on_kick(self, connection, event):
        target = event.arguments[0]
        if target == self.connection.get_nickname():
            logging.warning("Bot was kicked from the channel. Rejoining in 10 seconds...")
            connection.join(self.channel)


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

        except Exception as e:
            logging.error(f"[API Polling Error] {e}", exc_info=True)
        time.sleep(10)

def run_bot_forever():

    dcms = DCMS.DCMS("huan_bot_test", "P@ssword2010")
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