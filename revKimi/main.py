import json
from typing import Literal, Generator, Optional, Union
import requests

from .exceptions import *
from .config import Config


class Chatbot:
    """Kimi 聊天基类"""
    api_base = "https://kimi.moonshot.cn/api"

    def __init__(self, config_path: str = "./config.json"):
        self.config = Config(config_path)

    def __get_header(self, token_type: Literal["access_token", "refresh_token"]) -> dict[str, str]:
        """构建headers"""
        token = self.config[token_type]
        if not token:
            raise ConfigMissing(f"配置文件缺少{token_type}")
        headers = {
            "user-agent":
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.132 Safari/537.36',
            "Content-Type": "application/json",
            "Referer": "https://kimi.moonshot.cn",
            "Origin": "https://kimi.moonshot.cn",
            "Authorization": f"Bearer {token}"
        }
        return headers

    def __refresh_token(self):
        """刷新token"""
        resp = requests.get(
            url=self.api_base + "/auth/token/refresh",
            headers=self.__get_header("refresh_token")
        ).json()
        self.config["access_token"] = resp["access_token"]
        self.config["refresh_token"] = resp["refresh_token"]

    def __check_response(self, response: str):
        try:
            response_dict = json.loads(response)
            if response_dict.get("error_type") == "auth.token.invalid":
                self.__refresh_token()
        except Exception as e:
            return

    def __request(
            self,
            method: str,
            url: str,
            json: dict,
            stream: bool = False,
            **kwargs
    ) -> requests.Response:
        resp = requests.request(
            method=method,
            url=url,
            json=json,
            stream=stream,
            headers=self.__get_header("access_token"),
            **kwargs
        )
        stat_code = resp.status_code
        if stat_code != 401:
            return resp
        resp_json = resp.json()
        if resp_json.get("error_type") == "auth.token.invalid":
            self.__refresh_token()
            return requests.request(
                method=method,
                url=url,
                json=json,
                stream=stream,
                headers=self.__get_header("access_token"),
                **kwargs
            )

    def create_conversation(self, name: str) -> dict:
        """创建会话"""
        resp = self.__request(
            method="GET",
            url=self.api_base + "/chat",
            json={
                "name": f"{name}",
                "is_example": False,
                "born_from": ""
            }
        ).json()
        return resp

    def __stream_ask(
            self,
            prompt: str,
            conversation_id: Optional[str],
            timeout: int = 10,
            use_search: bool = False
    ) -> Generator[dict, None, None]:
        """流式提问

        :param prompt: 提问内容
        :param conversation_id: 会话id（若不填则会新建）
        :param timeout: 超时时间（默认10秒）
        :param use_search: 是否使用搜索

        """
        if not conversation_id:
            conversation_id = self.create_conversation("未命名")["id"]
        resp = self.__request(
            method="POST",
            url=self.api_base + f"/chat/{conversation_id}/completion/stream",
            timeout=timeout,
            stream=True,
            json={
                "kimiplus_id": "kimi",
                "messages": [{
                    "role": "user",
                    "content": prompt
                }],
                "refs": [],
                "use_search": use_search
            }
        )
        for chunk in resp.iter_lines():
            try:
                if chunk:
                    chunk = chunk.decode("utf-8")
                    if not chunk.endswith("}"):
                        continue
                    chunk_json = json.loads(chunk[6:])
                    yield chunk_json
            except Exception as e:
                pass

    def ask(
            self,
            prompt: str,
            conversation_id: Optional[str],
            timeout: int = 10,
            use_search: bool = False,
            stream: bool = False
    ) -> Union[dict, Generator[dict, None, None]]:
        """流式提问

        :param prompt: 提问内容
        :param conversation_id: 会话id（若不填则会新建）
        :param timeout: 超时时间（默认10秒）
        :param use_search: 是否使用搜索
        :param stream: 是否为流式

        """
        resp_generator = self.__stream_ask(
            prompt,
            conversation_id,
            timeout,
            use_search
        )
        if stream:
            return resp_generator
        else:
            content = ""
            for chunk in resp_generator:
                if chunk.get("event") == "cmpl":
                    content += chunk.get("text")
            return {
                "text": content
            }
