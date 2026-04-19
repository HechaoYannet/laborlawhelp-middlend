# 错误码与处理规范（与当前实现对齐）

## 1. 标准错误响应结构（非流式）

```json
{
  "code": "RATE_LIMITED",
  "message": "请求过于频繁，请稍后再试",
  "trace_id": "7ec43fd8-4fa4-4ae0-8f69-0c44f2b726d5",
  "retryable": true,
  "details": {}
}
```

说明：所有 `AppError` 和未捕获异常都会返回该结构。

## 2. HTTP 映射
| HTTP | 错误码 | 含义 | 建议重试 |
|---|---|---|---|
| 400 | `BAD_REQUEST` | 请求参数不合法 | 否 |
| 401 | `UNAUTHORIZED` | 缺少或无效认证信息 | 否 |
| 403 | `FORBIDDEN` | 无权访问目标案件/会话 | 否 |
| 404 | `CASE_NOT_FOUND` / `SESSION_NOT_FOUND` | 资源不存在 | 否 |
| 409 | `SESSION_LOCKED` | 同会话并发消息冲突 | 是 |
| 410 | `ANONYMOUS_SESSION_EXPIRED` | 会话已结束或不可继续聊天 | 否 |
| 429 | `RATE_LIMITED` | 触发限流 | 是 |
| 502 | `OH_SERVICE_ERROR` / `OH_PROTOCOL_ERROR` / `OH_UPSTREAM_4XX` / `OH_UPSTREAM_5XX` | OpenHarness 上游异常 | 视 `retryable` |
| 504 | `OH_UPSTREAM_TIMEOUT` | OpenHarness 上游超时 | 是 |
| 500 | `INTERNAL_ERROR` | 未分类服务端异常 | 否 |

## 3. SSE 流内错误帧

```text
event: error
data: {"code":"OH_UPSTREAM_TIMEOUT","message":"OpenHarness 请求超时","retryable":true,"trace_id":"..."}
```

说明：流式失败时服务器仍会发送 `message_end` 收尾。

## 4. 客户端重试建议
| 场景 | 推荐策略 |
|---|---|
| `SESSION_LOCKED` | 1 秒后重试，最多 3 次 |
| `RATE_LIMITED` | 1s -> 2s -> 4s |
| `OH_UPSTREAM_TIMEOUT` | 最多重试 1~2 次 |
| `OH_UPSTREAM_5XX` / `OH_SERVICE_ERROR` | 可重试 1 次，失败后提示人工介入 |
| `UNAUTHORIZED` / `FORBIDDEN` | 不重试，直接引导重新认证或返回列表 |

## 5. 审计与排障
- 统一以 `trace_id` 关联 API 日志、聊天审计日志与前端报错。
- 聊天回合审计事件当前使用：`turn_completed`、`turn_failed`。
