import json
import os

import requests
base_url = "https://dev.3g.cx/"


class DCMS:
    last_message_id = 0

    def __init__(self,username,password):
        self.username = username
        self.password = password

    def login(self):
        url = base_url + "api.php?action=login"
        data = {"nick": self.username, "password": self.password}
        res = requests.post(url=url, data=data)
        cookies_dict = requests.utils.dict_from_cookiejar(res.cookies)
        cookies_json = json.dumps(cookies_dict)

        data = res.json()

        if data["status"] == "success":
            print("Login Successful")
            with open("cookies.json", "w") as file:
                file.write(cookies_json)
            self.get_last_message_id()

        else:
            print("Login Failed")
            print(data["message"])

    def load_cookies(self):
        if os.path.exists("cookies.json"):
            with open("cookies.json", "r") as file:
                return json.load(file)
        else:
            print("Cookies file not found")
            return None

    def is_cookies_valid(self):
        url = base_url + "api.php"
        cookies = self.load_cookies()
        res = requests.post(url=url, cookies=cookies)
        data = res.json()
        if data["status"] == "success":
            return True
        else:
            return False

    def refresh_cookies(self):
        if not self.is_cookies_valid():
            self.login()


    def post_to_message_board(self, platform, name, message):
        msg = f"[{platform}] {name}: {message}"
        self.post_to_message_board_only_message(msg)


    def post_to_message_board_only_message(self, message):
        self.refresh_cookies()
        url = base_url + "api.php?action=guest-msg-add"
        data = {"msg": message}
        cookies = self.load_cookies()
        res = requests.post(url=url, cookies=cookies, data=data)
        if res.text.startswith("{\"status\":\"error\""):
            print("Error: "+res.text)
        #json_data = res.json()
        #if json_data["status"] == "error":
            #print("Error: " + json_data["message"])

    def get_message_board(self):
        self.refresh_cookies()
        url = base_url + "api.php?action=guest-msg-list&page=1"
        cookies = self.load_cookies()
        res = requests.get(url=url, cookies=cookies)
        #print(res.text)
        if res.text.startswith("{\"status\":\"error\""):
            print("Error: " + res.text)
            return None
        else:
            return res.text
    def get_new_message(self):
        global last_message_id
        new_messages = []

        content = self.get_message_board()
        if content is not None:
            messages = json.loads(content)["data"]
            for message in messages:
                #print(message)
                if message['id'] > last_message_id:
                    last_message_id = message['id']
                    new_messages.append(message)
            new_messages.reverse()
            return new_messages
        else:
            return None

    def get_last_message_id(self):
        global last_message_id
        content = self.get_message_board()
        if content is not None:
            messages = json.loads(content).get('data', [])
            last_message_id = messages[0]['id']


    def get_user_info(self, user_id: int):
        self.refresh_cookies()
        url = base_url + "api.php?action=user-info&id="+str(user_id)
        cookies = self.load_cookies()
        res = requests.get(url=url, cookies=cookies)
        if res.text.startswith("{\"status\":\"error\""):
            print("Error: " + res.text)
            return None
        else:
            return res.text

    def get_user_nickname(self, id):
         content = self.get_user_info(id)
         if content is not None:
             content = json.loads(content)
             return content['data']['nick']
         else:
             return None
