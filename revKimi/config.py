import json
import os

from .exceptions import *


class Config:
    """配置文件"""
    def __init__(self, filepath: str):
        self.__config_template = {
            "access_token": "",
            "refresh_token": ""
        }
        self.__filepath = filepath
        if not os.access(filepath, os.F_OK):
            with open(filepath, "w+") as f:
                json.dump(self.__config_template, f, indent=4)
                raise CreateFile("配置文件已创建，请先填写")
        else:
            with open(filepath, "r") as f:
                self.__content: dict = json.loads(f.read())

    def __save(self):
        with open(self.__filepath, "w") as f:
            json.dump(self.__content, f, indent=4)

    def __getitem__(self, item):
        return self.__content.get(item, None)

    def __setitem__(self, key, value):
        self.__content[key] = value
        self.__save()




