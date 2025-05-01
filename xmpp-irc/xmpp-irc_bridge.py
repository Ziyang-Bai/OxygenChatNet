import threading
import time
import datetime
import ssl
import logging
import xmpp
import irc.client
import irc.connection
import xml.etree.ElementTree as ET

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('Bridge')

# 状态控制变量
relay_enabled = threading.Event()
relay_enabled.set()
start_time = datetime.datetime.now()

# 已知标签前缀，用于避免重复封装
TAG_PREFIXES = ('INVAILD')
# 用于提取已有标签的消息段
EXTRACT_TAGS = ('[QQ]', '[XMPP]', '[DCMS]', '[WV]')

# 从 config.xml 加载配置
def load_config(config_path="config.xml"):
    tree = ET.parse(config_path)
    root = tree.getroot()
    config = {}
    for child in root:
        config[child.tag] = child.text
    return config

# 加载配置
config = load_config()

# IRC 设置
IRC_SERVER = config.get("IRC_SERVER")
IRC_PORT = int(config.get("IRC_PORT"))
IRC_NICK = config.get("IRC_NICK")
IRC_CHANNEL = config.get("IRC_CHANNEL")

# XMPP 设置
XMPP_JID = config.get("XMPP_JID")
XMPP_PASSWORD = config.get("XMPP_PASSWORD")
XMPP_ROOM = config.get("XMPP_ROOM")
XMPP_NICK = config.get("XMPP_NICK")

# 为旧版 xmpp 库 patch SSL
def wrap_socket(sock, keyfile=None, certfile=None, server_side=False,
                do_handshake_on_connect=True, suppress_ragged_eofs=True):
    context = ssl.create_default_context()
    context.check_hostname = False
    logger.debug("Wrapping socket with custom SSL context")
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
        logger.debug(f"Initialized XMPPBot: {jid} -> {room} as {nick}")

    def connect(self):
        logger.info("Connecting to XMPP server...")
        if not self.client.connect():
            logger.error("XMPP 连接失败")
            raise Exception("XMPP连接失败")
        logger.info("Authenticating XMPP...")
        if not self.client.auth(self.jid.getNode(), self.password):
            logger.error("XMPP 认证失败")
            raise Exception("XMPP认证失败")
        self.client.sendInitPresence()
        self.client.RegisterHandler('presence', self.on_presence)
        self.client.RegisterHandler('message', self.on_groupchat_message)
        self.join_room()
        logger.info(f"Join request sent to {self.room_jid}/{self.nick}, proceeding without explicit confirmation.")

    def join_room(self):
        pres = xmpp.Presence(to=f"{self.room_jid}/{self.nick}")
        x = xmpp.Node('x', {'xmlns': xmpp.NS_MUC})
        pres.addChild(node=x)
        logger.debug(f"Sending MUC join presence: {pres}")
        self.client.send(pres)

    def on_presence(self, conn, presence):
        frm = presence.getFrom()
        typ = presence.getType() or 'available'
        logger.debug(f"Presence received from {frm}: type={typ}, stanza={presence}")

    def send_message(self, message):
        to_jid = str(self.room_jid)
        logger.debug(f"XMPP sending to {to_jid}: {message}")
        msg = xmpp.Message(to=to_jid, body=message, typ='groupchat')
        self.client.send(msg)

    def on_groupchat_message(self, conn, msg):
        if msg.getType() == 'groupchat' and msg.getFrom().getResource() != self.nick:
            user = msg.getFrom().getResource()
            body = msg.getBody()
            logger.debug(f"XMPP message from {user}: {body}")
            if not body or body.startswith((';', '!')):
                return
            # 避免多次封装：如果已有标签前缀则跳过
            if any(body.startswith(tag) for tag in TAG_PREFIXES):
                logger.debug("Message already contains a tag, skipping relay.")
                return
            # 过滤并格式化
            if "[QQ]" in body:
                body = body[body.index("[QQ]"):]
            elif "[XMPP]" in body:
                body = body[body.index("[XMPP]"):]
            elif "[DCMS]" in body:
                body = body[body.index("[DCMS]"):]
            asis = body
            formatted = f"[XMPP] {user}: {asis}"
            logger.debug(f"Filtered XMPP message: {formatted}")
            if relay_enabled.is_set():
                logger.info(f"Relaying XMPP→IRC: {formatted}")
                try:
                    self.irc_send_callback(formatted)
                except Exception as e:
                    logger.error(f"Relay XMPP→IRC error: {e}")

    def handle_control(self, cmd):
        logger.info(f"XMPP control cmd: {cmd}")
        if cmd == 'on':
            relay_enabled.set()
            self.send_message(';Relay enabled')
        elif cmd == 'off':
            relay_enabled.clear()
            self.send_message(';Relay disabled')
        elif cmd == 'status':
            uptime = datetime.datetime.now() - start_time
            xmpp_status = 'connected' if self.client.isConnected() else 'disconnected'
            irc_status = 'unknown'
            try:
                irc_status = 'connected' if self.irc_send_callback.__self__.connection.is_connected() else 'disconnected'
            except:
                pass
            status_msg = (
                f";Status: {'enabled' if relay_enabled.is_set() else 'disabled'} | "
                f"Uptime: {str(uptime).split('.')[0]} | IRC: {irc_status} | XMPP: {xmpp_status}"
            )
            self.send_message(status_msg)
            logger.debug(f"Status: {status_msg}")

    def process(self):
        while True:
            try:
                self.client.Process(1)
            except Exception as e:
                logger.error(f"XMPP processing error: {e}")
                time.sleep(5)

class IRCBot:
    def __init__(self, server, port, nickname, channel, xmpp_bot):
        self.reactor = irc.client.Reactor()
        self.connection = self.reactor.server().connect(server, port, nickname)
        self.connection.add_global_handler('welcome', self.on_connect)
        self.connection.add_global_handler('pubmsg', self.on_pubmsg)
        self.xmpp_bot = xmpp_bot
        self.channel = channel

    def on_connect(self, connection, event):
        logger.info(f"IRC joined channel {self.channel}")
        connection.join(self.channel)

    def on_pubmsg(self, connection, event):
        msg = event.arguments[0]
        user = event.source.nick
        logger.debug(f"IRC message from {user}: {msg}")
        # 控制前缀过滤
        if msg.startswith((';', '!')):
            return
        # 如果消息中包含已知标签段，则提取该段并转发
        for tag in EXTRACT_TAGS:
            idx = msg.find(tag)
            if idx != -1:
                extracted = msg[idx:]
                logger.info(f"Relaying IRC→XMPP extracted tag segment: {extracted}")
                try:
                    self.xmpp_bot.send_message(extracted)
                except Exception as e:
                    logger.error(f"Relay IRC→XMPP error: {e}")
                return
        # 否则正常封装转发
        formatted = f"[IRC] {user}: {msg}"
        logger.info(f"Relaying IRC→XMPP: {formatted}")
        try:
            self.xmpp_bot.send_message(formatted)
        except Exception as e:
            logger.error(f"Relay IRC→XMPP error: {e}")

    def send_to_irc(self, message):
        logger.debug(f"IRC sending: {message}")
        try:
            self.connection.privmsg(self.channel, message)
            logger.info(f"Sent to IRC: {message}")
        except Exception as e:
            logger.error(f"IRC send error: {e}")

    def start(self):
        try:
            logger.info("Starting IRC loop")
            self.reactor.process_forever()
        except Exception as e:
            logger.error(f"IRC loop error: {e}")


def run_xmpp_bot(xmpp_bot):
    xmpp_bot.connect()
    xmpp_bot.process()


def main():
    irc_bot = None
    def irc_send(msg):
        if irc_bot:
            irc_bot.send_to_irc(msg)

    xmpp_bot = XMPPBot(XMPP_JID, XMPP_PASSWORD, XMPP_ROOM, XMPP_NICK, irc_send)
    threading.Thread(target=run_xmpp_bot, args=(xmpp_bot,), daemon=True).start()
    time.sleep(2)
    irc_bot = IRCBot(IRC_SERVER, IRC_PORT, IRC_NICK, IRC_CHANNEL, xmpp_bot)
    xmpp_bot.irc_send_callback = irc_bot.send_to_irc
    irc_bot.start()

if __name__ == '__main__':
    main()
