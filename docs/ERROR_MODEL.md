# 错误模型

API 领域错误同时保留旧客户端使用的 `detail`，并返回结构化 `error`：

```json
{
  "detail": "数据中不存在这些列: ['yield']",
  "error": {
    "code": "invalid_plan",
    "message": "数据中不存在这些列: ['yield']",
    "issues": [
      {
        "code": "missing_columns",
        "severity": "error",
        "field": "columns",
        "message": "数据中不存在这些列: ['yield']",
        "details": {"columns": ["yield"]}
      }
    ],
    "details": {}
  }
}
```

稳定错误代码包括：`invalid_plan`、`invalid_dataset`、`method_unavailable`、`execution_failed`、`resource_not_found`、`workspace_conflict`、`unsupported_file`、`file_too_large` 和 `report_failed`。
