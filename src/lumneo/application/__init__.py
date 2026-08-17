# lumneo/application/__init__.py
# 应用层：聚合“管理/资源”域的统一对外门面（ApplicationFacade）。
#
# 与 conversation/facade（对话域）并列。API 路由通过 request.app.state.resource_facade
# 访问本层，遵循“薄路由 → 门面（边界）→ Repository 端口 / 基础设施适配器”的分层。
