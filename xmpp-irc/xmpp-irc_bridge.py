import threading
import time
import datetime
import ssl
import xmpp
import irc.client
import irc.connection
import xml.etree.ElementTree as ET  # 用于解析 XML 配置文件

# 从 XML 配置文件加载配置
def load_config(file_path):
    tree = ET.parse(file_path)
    root = tree.getroot()
    irc_config = root.find("irc")
    xmpp_config = root.find("xmpp")
    return {
        "irc": {
            "server": irc_config.find("server").text,
            "port": int(irc_config.find("port").text),
            "nickname": irc_config.find("nickname").text,
            "channel": irc_config.find("channel").text,
        },
        "xmpp": {
            "jid": xmpp_config.find("jid").text,
            "password": xmpp_config.find("password").text,
            "room": xmpp_config.find("room").text,
            "nick": xmpp_config.find("nick").text,
        },
    }

# 加载配置
config = load_config("config.xml")

# 状态控制变量
relay_enabled = threading.Event()
relay_enabled.set()
start_time = datetime.datetime.now()

# 使用配置文件中的值
IRC_SERVER = config["irc"]["server"]
IRC_PORT = config["irc"]["port"]
IRC_NICK = config["irc"]["nickname"]
IRC_CHANNEL = config["irc"]["channel"]

XMPP_JID = config["xmpp"]["jid"]
XMPP_PASSWORD = config["xmpp"]["password"]
XMPP_ROOM = config["xmpp"]["room"]
XMPP_NICK = config["xmpp"]["nick"]

# 为旧版 xmpp 库 patch SSL
def wrap_socket(sock, keyfile=None, certfile=None, server_side=False,
                do_handshake_on_connect=True, suppress_ragged_eofs=True):
    context = ssl.create_default_context()
    context.check_hostname = False
    return context.wrap_socket(sock, server_hostname=None)

ssl.wrap_socket = wrap_socket

class XMPPBot:
    def __init__(self, jid, password, room, nick, irc_send_callback=None):
        self.client = xmpp.Client(jid.split("@")[1], debug=[])
        self.jid = xmpp.JID(jid)
        self.password = password
        self.room_jid = xmpp.JID(room)
        self.nick = nick
        self.irc_send_callback = irc_send_callback

    def connect(self):
        if not self.client.connect():
            raise Exception("XMPP连接失败")
        if not self.client.auth(self.jid.getNode(), self.password):
            raise Exception("XMPP认证失败")
        self.client.sendInitPresence()
        self.join_room()
        # 注册 groupchat 消息处理
        self.client.RegisterHandler('message', self.on_groupchat_message)

    def join_room(self):
        presence = xmpp.Presence(to=f"{self.room_jid}/{self.nick}")
        self.client.send(presence)
        print(f"Joined XMPP room {self.room_jid}")

    def send_message(self, message):
        to_jid = str(self.room_jid) 
        msg = xmpp.Message(to=to_jid, body=message, typ='groupchat')
        self.client.send(msg)

    def on_groupchat_message(self, conn, msg):
        if msg.getType() == 'groupchat' and msg.getFrom().getResource() != self.nick:
            user = msg.getFrom().getResource()
            body = msg.getBody()
            
            if body:
                # 不转发以分号开头的消息和命令
                if body.startswith(';') or body.startswith('!'):
                    return

                if body.startswith("!ircxmpp"):  
                    cmd = body[8:].strip()
                    if cmd == "on":
                        relay_enabled.set()
                        self.send_message(";Relay enabled")
                    elif cmd == "off":
                        relay_enabled.clear()
                        self.send_message(";Relay disabled")
                    elif cmd == "status":
                        status = "enabled" if relay_enabled.is_set() else "disabled"
                        uptime = datetime.datetime.now() - start_time
                        xmpp_status = "connected" if self.client.isConnected() else "disconnected"
                        irc_status = "unknown"
                        if self.irc_send_callback and hasattr(self.irc_send_callback, '__self__'):
                            irc_bot = self.irc_send_callback.__self__
                            if hasattr(irc_bot, 'connection'):
                                irc_status = "connected" if irc_bot.connection.is_connected() else "disconnected"
                        self.send_message(
                            f";Status: {status} | Online: {str(uptime).split('.')[0]} | IRC: {irc_status} | XMPP: {xmpp_status}"
                        )
                    return

                if relay_enabled.is_set():
                    formatted = f"[XMPP] {user}: {body}"
                    print(f"Received message from XMPP: {formatted}")
                    if self.irc_send_callback:
                        self.irc_send_callback(formatted)

    def process(self):
        while True:
            self.client.Process(1)

class IRCBot:
    def __init__(self, server, port, nickname, channel, xmpp_bot):
        self.server = server
        self.port = port
        self.nickname = nickname
        self.channel = channel
        self.xmpp_bot = xmpp_bot
        self.reactor = irc.client.Reactor()
        self.connection = self.reactor.server().connect(server, port, nickname)
        self.connection.add_global_handler("welcome", self.on_connect)
        self.connection.add_global_handler("pubmsg", self.on_pubmsg)

    def on_connect(self, connection, event):
        connection.join(self.channel)
        print("Joined IRC channel", self.channel)

    def on_pubmsg(self, connection, event):
        message = event.arguments[0]
        sender = event.source.nick

        # 不转发以分号开头的消息和命令
        if message.startswith(';') or message.startswith('!'):
            return
        
        formatted = f"[IRC] {sender}: {message}"
        if relay_enabled.is_set():
            self.xmpp_bot.send_message(formatted)

    def send_to_irc(self, message: str) -> None:
        # 供 XMPP bot 调用
        self.connection.privmsg(self.channel, message)

    def start(self) -> None:
        # 启动IRC机器人的主事件循环
        self.reactor.process_forever()

def run_xmpp_bot(xmpp_bot: XMPPBot) -> None:
    # 启动XMPP机器人的工作线程函数
    xmpp_bot.connect()
    xmpp_bot.process()

def main() -> None:
    # 主函数，负责初始化和启动两个机器人
    irc_bot = None  # 声明IRC机器人变量

    def irc_send_callback(msg: str) -> None:
        # 初始回调函数
        if irc_bot:
            irc_bot.send_to_irc(msg)

    # 创建XMPP机器人实例
    xmpp_bot = XMPPBot(XMPP_JID, XMPP_PASSWORD, XMPP_ROOM, XMPP_NICK, irc_send_callback=irc_send_callback)

    # 在新线程中启动XMPP机器人
    xmpp_thread = threading.Thread(target=run_xmpp_bot, args=(xmpp_bot,))
    xmpp_thread.daemon = True  # 设置为守护线程，主程序退出时自动结束
    xmpp_thread.start()

    time.sleep(2)  # 等待XMPP连接建立

    nonlocal_irc_bot = {}  #
    irc_bot = IRCBot(IRC_SERVER, IRC_PORT, IRC_NICK, IRC_CHANNEL, xmpp_bot)
    nonlocal_irc_bot['bot'] = irc_bot

    # 更新XMPP机器人的回调函数，使用新的IRC机器人实例
    def irc_send_callback2(msg):
        nonlocal_irc_bot['bot'].send_to_irc(msg)
    xmpp_bot.irc_send_callback = irc_send_callback2

    # 启动IRC机器人（注意阻塞主线程）
    irc_bot.start()

if __name__ == "__main__":
    main()
