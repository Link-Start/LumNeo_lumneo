# backend/services/tool_execution/suggestion.py
class SuggestionGenerator:
    @staticmethod
    def generate(error_message: str) -> str:
        error_lower = error_message.lower()
        if "timeout" in error_lower or "timed out" in error_lower or "超时" in error_message:
            return "工具执行超时，可尝试延长超时时间或检查网络延迟"
        if "connection" in error_lower or "network" in error_lower or "无法连接" in error_message:
            return "网络连接异常，请检查网络或后端服务是否可达"
        if "permission" in error_lower or "denied" in error_lower or "权限" in error_message:
            return "权限不足，请检查工具认证或授权配置"
        if "argument" in error_lower or "parameter" in error_lower or "参数" in error_message:
            return "工具参数错误，请检查输入格式或联系管理员"
        if "not found" in error_lower or "不存在" in error_message:
            return "目标资源不存在，请确认工具所需的前置条件"
        if "internal" in error_lower or "server" in error_lower or "内部" in error_message:
            return "工具后端服务异常，请稍后重试或联系管理员"
        return "工具执行失败，请检查工具参数、网络连接，或查看详细错误信息后重试"