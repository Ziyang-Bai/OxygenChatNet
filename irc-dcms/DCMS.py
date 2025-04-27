from typing import Optional, List, Dict, Any
import json

import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry

BASE_URL = "https://dev.3g.cx/"

class DCMS:
    """DCMS API客户端，用于与留言板系统交互。"""

    room_id = 4

    retry_strategy = Retry(
        total=3,  # 最大重试次数
        backoff_factor=1,  # 延迟倍数，每次重试会增加延迟时间
        status_forcelist=[500, 502, 503, 504],  # 对于这些状态码进行重试
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)

    # 创建一个会话并使用该适配器
    session = requests.Session()
    session.mount("https://", adapter)
    
    def __init__(self, username: str, password: str) -> None:
        """
        初始化DCMS客户端。
        
        Args:
            username: 用户名
            password: 密码
        """
        self.username = username
        self.password = password
        self._last_message_id = 0
        
    def login(self) -> bool:
        """
        登录DCMS系统。
        Returns:
            bool: 登录是否成功
        """
        url = f"{BASE_URL}api.php?action=login"
        data = {"nick": self.username, "password": self.password}
        
        response = requests.post(url=url, data=data, timeout=5)
        cookies = requests.utils.dict_from_cookiejar(response.cookies)
        
        data = response.json()
        if data["status"] != "success":
            print(f"登录失败: {data['message']}")
            return False
            
        with open("cookies.json", "w") as f:
            json.dump(cookies, f)
        
        self._get_last_message_id_from_room()
        print("登录成功")
        return True

    def _load_cookies(self) -> Optional[Dict[str, str]]:
        """加载cookies文件。"""
        try:
            with open("cookies.json") as f:
                return json.load(f)
        except FileNotFoundError:
            print("未找到cookies文件")
            return None

    def _is_cookies_valid(self) -> bool:
        """验证cookies是否有效。"""
        cookies = self._load_cookies()
        if not cookies:
            return False
            
        response = requests.post(f"{BASE_URL}api.php", cookies=cookies,timeout=5)
        return response.json().get("status") == "success"

    def refresh_cookies(self) -> None:
        """刷新无效的cookies。"""
        if not self._is_cookies_valid():
            self.login()

    def post_message(self, message: str, platform: str = "", name: str = "") -> None:
        """
        发送消息到留言板。
        
        Args:
            message: 消息内容
            platform: 可选，平台标识
            name: 可选，发送者名称
        """
        if platform and name:
            message = f"[{platform}] {name}: {message}"
            
        self.refresh_cookies()
        url = f"{BASE_URL}api.php?action=guest-msg-add"
        response = requests.post(
            url=url,
            cookies=self._load_cookies(),
            data={"msg": message},
            timeout = 5
        )
        
        if response.text.startswith('{"status":"error"'):
            print(f"错误: {response.text}")

    def get_message_board(self) -> Optional[List[Dict[str, Any]]]:
        """获取留言板消息。"""
        self.refresh_cookies()
        url = f"{BASE_URL}api.php?action=guest-msg-list&page=1"
        response = requests.get(url=url, cookies=self._load_cookies(),timeout=5)
        
        if response.text.startswith('{"status":"error"'):
            print(f"错误: {response.text}")
            return None
            
        return response.json().get("data", [])

    def get_new_messages(self) -> List[Dict[str, Any]]:
        """
        获取自上次检查以来的新消息。
        
        Returns:
            List 新消息的列表
        """
        new_messages = []
        messages = self.get_message_board()
        
        for message in messages:

            if message['id'] > self._last_message_id:
                self._last_message_id = message['id']
                new_messages.append(message)
                
        new_messages.reverse()
        return new_messages

    def _get_last_message_id(self) -> None:
        """获取最后一条消息的ID。"""
        messages = self.get_message_board()
        if messages:
            self._last_message_id = messages[0]['id']

    def post_message_room(self, message: str, platform: str = "", name: str = "") -> None:
        """
        发送消息到聊天室。

        Args:
            message: 消息内容
            platform: 可选，平台标识
            name: 可选，发送者名称
        """

        if platform and name:
            message = f"[{platform}] {name}: {message}"

        self.refresh_cookies()
        url = f"{BASE_URL}api.php?action=chat-msg-add&room={self.room_id}"
        #print(url)
        response = requests.post(
            url=url,
            cookies=self._load_cookies(),
            data={"msg": message},
            timeout=5
        )

        if response.text.startswith('{"status":"error"'):
            print(f"错误: {response.text}")
        else:
            self._last_message_id = int(response.json()["id"])

    def get_message_room(self) -> Optional[List[Dict[str, Any]]]:
        """获取聊天室消息。"""
        self.refresh_cookies()
        url = f"{BASE_URL}api.php?action=chat-msg-list&room={self.room_id}&page=1"
        #print(url)
        response = requests.get(url=url, cookies=self._load_cookies(),timeout=5)

        if response.text.startswith('{"status":"error"'):
            print(f"错误: {response.text}")
            return None

        return response.json().get("data", [])

    def get_new_messages_from_room(self) -> List[Dict[str, Any]]:
        """
        获取自上次检查以来的聊天室新消息。

        Returns:
            List 新消息的列表
        """
        new_messages = []
        messages = self.get_message_room()

        for message in messages:
            if message['id'] > self._last_message_id:
                self._last_message_id = message['id']
                new_messages.append(message)

        new_messages.reverse()
        return new_messages

    def _get_last_message_id_from_room(self) -> None:
        """获取最后一条消息的ID。"""
        messages = self.get_message_room()
        if messages:
            self._last_message_id = messages[0]['id']

    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        获取用户信息。
        
        Args:
            user_id: 用户ID
            
        Returns:
            Dict 包含用户信息的字典，失败时返回None
        """
        self.refresh_cookies()
        url = f"{BASE_URL}api.php?action=user-info&id={user_id}"
        response = requests.get(url=url, cookies=self._load_cookies(),timeout=5)
        
        if response.text.startswith('{"status":"error"'):
            print(f"错误: {response.text}")
            return None
            
        return response.json()

    def get_user_nickname(self, user_id: int) -> Optional[str]:
        """
        获取用户昵称。
        
        Args:
            user_id: 用户ID
            
        Returns:
            str: 用户昵称，获取失败时返回None
        """
        user_info = self.get_user_info(user_id)
        return user_info['data']['nick'] if user_info else None
