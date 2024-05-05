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
        if not os.access(filepath, os.F_OK):
            self.file = open(filepath, "w+")
            json.dump(self.__config_template, self.file, indent=4)
            raise CreateFile("配置文件已创建，请先填写")
        else:
            self.file = open(filepath, "r+")
            self.__content: dict = json.loads(self.file.read())

    def __del__(self):
        self.file.close()

    def __save(self):
        self.file.seek(0)
        self.file.write(json.dumps(self.__content, indent=4))
        self.file.flush()

    def __getitem__(self, item):
        return self.__content.get(item, None)

    def __setitem__(self, key, value):
        self.__content[key] = value
        self.__save()




