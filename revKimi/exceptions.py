class CreateFile(Exception):
    """创建配置文件"""
    pass


class ConfigMissing(Exception):
    """缺少配置项"""
    pass


class UploadError(Exception):
    """上传错误"""
    pass


class UnexpectedResponse(Exception):
    """不正常响应"""
    pass
