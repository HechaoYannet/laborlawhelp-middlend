# 可观测性与告警

## 1. 结构化日志字段
必填 JSON 字段：
- `timestamp`
- `trace_id`
- `owner_type`
- `owner_id`
- `session_id`
- `event`
- `duration_ms`
- `fallback`
- `error_code`（如有）

## 2. 指标
| 指标 | 类型 | 目标 |
|---|---|---|
| active_sse_connections | gauge | 关注趋势变化 |
| chat_first_token_ms | histogram | `p95` 低于阈值 |
| chat_full_response_ms | histogram | `p95` 低于阈值 |
| oh_success_rate | gauge | 预发布环境 `>= 99%` |
| rate_limited_count | counter | 突增时告警 |
| session_locked_count | counter | 突增时告警 |
| fallback_triggered_count | counter | 应接近 0 |

## 3. 告警建议
| 告警项 | 条件 | 严重级别 |
|---|---|---|
| OpenHarness 服务退化 | `oh_success_rate < 95% for 5m` | 高 |
| 流式延迟偏高 | `chat_first_token_ms p95 > 3000ms for 10m` | 中 |
| 错误突增 | `5xx rate > 3% for 5m` | 高 |
| 锁冲突突增 | `session_locked_count > baseline*3` | 中 |

## 4. 链路关联
- 让 `X-Trace-Id` 在 API -> service -> adapter -> audit 全链路透传。
- 如果客户端未携带，则在入口生成 UUID。

## 5. 看板布局
1. 流量与连接数面板
2. 延迟面板（首 token / 完整回复）
3. 错误与重试面板
4. 依赖健康面板
5. 降级与锁冲突面板
