import json
from typing import Literal, Generator, Optional, Union
import requests
import filetype
import hashlib

from .exceptions import *
from .config import Config


class Chatbot:
    """Kimi 聊天基类"""
    api_base = "https://kimi.moonshot.cn/api"

    def __init__(self, config_obj: object = None, config_path: str = "./config.json"):
        """
        初始化
            config_obj: 可自定义的配置文件对象，以便于与其他配置文件对接，须实现__getitem__和__setitem__方法，
            若不传入，则使用默认配置文件对象
        """
        if config_obj:
            self.config = config_obj
        else:
            self.config = Config(config_path)

    def __get_header(self, token_type: Literal["access_token", "refresh_token"], other: dict = None) -> dict[str, str]:
        """构建headers"""
        if other is None:
            other = {}
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
                  } | other
        return headers

    def __refresh_token(self):
        """刷新token"""
        resp = requests.get(
            url=self.api_base + "/auth/token/refresh",
            headers=self.__get_header("refresh_token")
        ).json()
        self.config["access_token"] = resp["access_token"]
        self.config["refresh_token"] = resp["refresh_token"]

    def __request(
            self,
            method: str,
            url: str,
            stream: bool = False,
            headers: dict = None,
            **kwargs
    ) -> requests.Response:
        resp = requests.request(
            method=method,
            url=url,
            stream=stream,
            headers=self.__get_header("access_token", headers),
            **kwargs
        )
        stat_code = resp.status_code
        if stat_code == 200:
            return resp
        resp_json = resp.json()
        if resp_json.get("error_type") == "auth.token.invalid":
            # token过期
            self.__refresh_token()
            return requests.request(
                method=method,
                url=url,
                stream=stream,
                headers=self.__get_header("access_token", headers),
                **kwargs
            )
        else:
            raise UnexpectedResponse(str(resp_json))

    def create_conversation(self, name: str = "未命名会话") -> dict:
        """创建会话"""
        resp = self.__request(
            method="POST",
            url=self.api_base + "/chat",
            json={
                "name": f"{name}",
                "is_example": False,
                "born_from": ""
            }
        ).json()
        return resp

    def delete_conversation(self, conversation_id: str) -> None:
        """删除会话"""
        self.__request(
            method="DELETE",
            url=self.api_base + f"/chat/{conversation_id}"
        )

    def get_conversations(self, size: int = 30) -> dict:
        """获取会话列表
        :param size: 最多获取条数（默认30）
        """
        resp = self.__request(
            method="POST",
            url=self.api_base + "/chat/list",
            json={
                "kimiplus_id": "",
                "offset": 0,
                "size": size
            }
        ).json()
        return resp

    def get_history(self, conversation_id: str, last: int = 50) -> dict:
        """获取会话历史
        :param conversation_id: 会话ID
        :param last: 历史条数（默认50）
        """
        resp = self.__request(
            method="POST",
            url=self.api_base + f"/chat/{conversation_id}/segment/scroll",
            json={
                "last": last
            }
        ).json()
        return resp

    def __get_presign_url(self, file_name: str) -> dict:
        """获取上传文件预签名url
        :param file_name: 文件名
        """
        resp = self.__request(
            method="POST",
            url=self.api_base + "/pre-sign-url",
            json={
                "action": "file",
                "name": file_name
            }
        ).json()
        return resp

    def __get_file_info(self, file_name: str, object_name: str) -> dict:
        """获取文件信息"""
        resp = self.__request(
            method="POST",
            url=self.api_base + "/file",
            json={
                "name": file_name,
                "object_name": object_name,
                "type": "file"
            }
        ).json()
        return resp

    def __parse_file(self, file_info: dict) -> None:
        """解析文件"""
        resp = self.__request(
            method="POST",
            url=self.api_base + "/file/parse_process",
            json={
                "ids": [file_info["id"]]
            },
            stream=True
        )
        message = None
        for line in resp.iter_lines():
            if line:
                message = json.loads(line.decode("utf-8")[6:])
        if message and message["status"] == "parsed":
            return
        else:
            raise UploadError(f"Parse failed: {message}")

    def __upload_file(self, file: bytes) -> dict:
        """上传文件
        :param file: 文件二进制数据
        """

        file_type = filetype.guess_mime(file)
        file_name = "" + hashlib.md5(file).hexdigest() + "." + file_type.split("/")[1]

        presign_url = self.__get_presign_url(file_name)
        self.__request(
            method="PUT",
            url=presign_url["url"],
            data=file,
            headers={
                "Content-Type": file_type,
                "Content-Length": str(len(file))
            }
        )

        file_info = self.__get_file_info(file_name, presign_url["object_name"])
        self.__parse_file(file_info)

        return file_info

    def __stream_ask(
            self,
            prompt: str,
            conversation_id: Optional[str],
            timeout: int = 10,
            use_search: bool = False,
            file: bytes = None
    ) -> Generator[dict, None, None]:
        """流式提问

        :param prompt: 提问内容
        :param conversation_id: 会话id（若不填则会新建）
        :param timeout: 超时时间（默认10秒）
        :param use_search: 是否使用搜索
        :param file: 文件二进制数据

        """
        request_json = {
            "kimiplus_id": "kimi",
            "messages": [{
                "role": "user",
                "content": prompt
            }],
            "refs": [],
            "use_search": use_search
        }

        if file:
            file_info = self.__upload_file(file)
            request_json["refs"] = [file_info["id"]]
        if not conversation_id:
            conversation_id = self.create_conversation()["id"]
        resp = self.__request(
            method="POST",
            url=self.api_base + f"/chat/{conversation_id}/completion/stream",
            timeout=timeout,
            stream=True,
            json=request_json
        )
        reply_text = ""
        for chunk in resp.iter_lines():
            try:
                if chunk:
                    # 非空chunk
                    chunk = chunk.decode("utf-8")
                    if not chunk.endswith("}"):
                        # 不完整
                        continue
                    chunk_json = json.loads(chunk[6:])
                    if chunk_json.get("event") == "cmpl":
                        reply_text += chunk_json.get("text")
                        result = {
                            "conversation_id": conversation_id,
                            "text": reply_text
                        }
                        yield result
            except Exception as e:
                pass

    def ask(
            self,
            prompt: str,
            conversation_id: Optional[str],
            timeout: int = 10,
            use_search: bool = False,
            stream: bool = False,
            file: bytes = None
    ) -> Union[dict, Generator[dict, None, None]]:
        """流式提问

        :param prompt: 提问内容
        :param conversation_id: 会话id（若不填则会新建）
        :param timeout: 超时时间（默认10秒）
        :param use_search: 是否使用搜索
        :param stream: 是否为流式
        :param file: 文件二进制数据（传入代表上传文件）

        """
        resp_generator = self.__stream_ask(
                            prompt,
                            conversation_id,
                            timeout,
            use_search,
            file
                        )
        if stream:
            return resp_generator
        else:
            result = None
            for chunk in resp_generator:
                result = chunk
            return result
