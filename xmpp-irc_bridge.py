import threading
import time
import datetime
import ssl
import xmpp
import irc.client
import irc.connection
# 这辈子都不再用slixmpp了
# 真疯了
# 状态控制变量 
relay_enabled = threading.Event()
relay_enabled.set()
start_time = datetime.datetime.now()

# IRC 设置
IRC_SERVER = "chat.freenode.net"
IRC_PORT = 6667
IRC_NICK = "ircxmpp_bridge"
IRC_CHANNEL = "#dcms"

# XMPP 设置
XMPP_JID = "xmppirc_bridge@xmpp.jp"
XMPP_PASSWORD = "123456"
XMPP_ROOM = "dcms@conference.xmpp.jp"
XMPP_NICK = "xmppirc_bridge"

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
        # 只处理群聊消息
        if msg.getType() == 'groupchat' and msg.getFrom().getResource() != self.nick:
            user = msg.getFrom().getResource()
            body = msg.getBody()
            if body:
                # 指令处理
                if body == "?on":
                    relay_enabled.set()
                    self.send_message("Enabled relay")
                    return
                elif body == "?off":
                    relay_enabled.clear()
                    self.send_message("Disabled relay")
                    return
                elif body == "?status":
                    status = "enabled" if relay_enabled.is_set() else "disabled"
                    uptime = datetime.datetime.now() - start_time
                    xmpp_status = "connected" if self.client.isConnected() else "disconnected"
                    irc_status = "unknown"
                    if self.irc_send_callback and hasattr(self.irc_send_callback, '__self__'):
                        irc_bot = self.irc_send_callback.__self__
                        if hasattr(irc_bot, 'connection'):
                            irc_status = "connected" if irc_bot.connection.is_connected() else "disconnected"
                    self.send_message(
                        f"Status：{status} | Online：{str(uptime).split('.')[0]} | IRC: {irc_status} | XMPP: {xmpp_status}"
                    )
                    return
                # 非指令才转发，且relay_enabled为True才转发
                if relay_enabled.is_set():
                    formatted = f"[XMPP] {user}: {body}"
                    print(f"Received message from XMPP: {formatted}")  # 调试输出
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
        formatted = f"[IRC] {sender}: {message}"
        
        # 调试信息
        print(f"Received message from IRC: {formatted}")  # 输出收到的 IRC 消息

        if message == "?on":
            relay_enabled.set()
            connection.privmsg(self.channel, "Enabled relay")
            return
        elif message == "?off":
            relay_enabled.clear()
            connection.privmsg(self.channel, "Disabled relay")
            return
        elif message == "?status":
            status = "enabled" if relay_enabled.is_set() else "disabled"
            uptime = datetime.datetime.now() - start_time
            xmpp_status = "connected" if self.xmpp_bot.client.isConnected() else "disconnected"
            irc_status = "connected" if self.connection.is_connected() else "disconnected"
            connection.privmsg(
                self.channel,
                f"Status：{status} | Online：{str(uptime).split('.')[0]} | IRC: {irc_status} | XMPP: {xmpp_status}"
            )
            return

        if relay_enabled.is_set():
            if message.startswith("[QQ] ") or message.startswith("[DCMS] "):
                formatted = message
            else:
                formatted = f"[IRC] {sender}: {message}"
            self.xmpp_bot.send_message(formatted)

    def send_to_irc(self, message):
        # 供 XMPP bot 调用
        self.connection.privmsg(self.channel, message)

    def start(self):
        self.reactor.process_forever()

def run_xmpp_bot(xmpp_bot):
    xmpp_bot.connect()
    xmpp_bot.process()

def main():
    irc_bot = None  # 先声明

    def irc_send_callback(msg):
        if irc_bot:
            irc_bot.send_to_irc(msg)

    xmpp_bot = XMPPBot(XMPP_JID, XMPP_PASSWORD, XMPP_ROOM, XMPP_NICK, irc_send_callback=irc_send_callback)

    xmpp_thread = threading.Thread(target=run_xmpp_bot, args=(xmpp_bot,))
    xmpp_thread.daemon = True
    xmpp_thread.start()

    time.sleep(2)

    # 现在初始化 irc_bot，并将其赋值给外部变量
    nonlocal_irc_bot = {}
    irc_bot = IRCBot(IRC_SERVER, IRC_PORT, IRC_NICK, IRC_CHANNEL, xmpp_bot)
    nonlocal_irc_bot['bot'] = irc_bot

    # 更新回调中的 irc_bot
    def irc_send_callback2(msg):
        nonlocal_irc_bot['bot'].send_to_irc(msg)
    xmpp_bot.irc_send_callback = irc_send_callback2

    irc_bot.start()

if __name__ == "__main__":
    main()
