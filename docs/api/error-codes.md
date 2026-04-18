# 错误码与处理规范

## 1. HTTP 映射
| HTTP | 错误码 | 含义 | 是否建议重试 | 前端处理建议 |
|---|---|---|---|---|
| 400 | `BAD_REQUEST` | 请求参数不合法 | 否 | 提示用户修正输入 |
| 401 | `UNAUTHORIZED` | 认证失败或过期 | 否 | 二期引导重新登录 |
| 403 | `FORBIDDEN` | 无权访问目标案件/会话 | 否 | 返回列表页并提示权限不足 |
| 409 | `SESSION_LOCKED` | 同会话并发消息冲突 | 是 | 退避后重试 |
| 410 | `ANONYMOUS_SESSION_EXPIRED` | 游客会话已结束/过期 | 否 | 创建新会话 |
| 429 | `RATE_LIMITED` | 触发限流 | 是 | 指数退避 |
| 500 | `OH_SERVICE_ERROR` | OpenHarness 调用异常 | 是 | 友好提示后重试 |
| 503 | `SERVICE_UNAVAILABLE` | 依赖服务不可用 | 是 | 降级提示并建议稍后重试 |

## 2. 错误响应包结构

```json
{
  "code": "RATE_LIMITED",
  "message": "请求过于频繁，请稍后再试",
  "trace_id": "7ec43fd8-4fa4-4ae0-8f69-0c44f2b726d5",
  "retryable": true,
  "details": {}
}
```

## 3. SSE 流内错误帧

服务端在中断流前应尽量发送：

```text
event: error
data: {"code":503,"message":"服务暂时不可用，您可稍后重试。","retryable":true}
```

## 4. 客户端重试策略
| 场景 | 推荐策略 |
|---|---|
| `SESSION_LOCKED` | 1 秒后重试，最多 3 次 |
| `RATE_LIMITED` | 1s -> 2s -> 4s，超过后停止 |
| `OH_SERVICE_ERROR` | 最多重试 1 次，失败则提示人工处理 |
| `SERVICE_UNAVAILABLE` | 2 秒后重试 1 次，仍失败则停止 |

## 5. 日志与审计要求
- 所有错误响应都必须包含 `trace_id`。
- `audit_logs` 需记录错误码和摘要信息。
- 流式错误建议附带最近一次 `seq`，用于复盘断流位置。
