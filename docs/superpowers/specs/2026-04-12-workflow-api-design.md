# Workflow API Design

**Date:** 2026-04-12

## Goal

Thêm một lớp API HTTP tối thiểu bằng FastAPI để start, query, và review `DocumentWorkflow` đang chạy trên Temporal mà không làm thay đổi nguyên tắc kiến trúc hiện có: workflow state chỉ giữ `ArtifactRef` và metadata nhỏ.

## Scope

Phiên bản đầu chỉ hỗ trợ 6 API:

- `POST /workflows/start`
- `GET /workflows/{document_id}/status`
- `GET /workflows/{document_id}/snapshot`
- `POST /workflows/{document_id}/reviews/ir`
- `POST /workflows/{document_id}/reviews/final`
- `POST /workflows/{document_id}/artifacts/ir-update`

Ngoài phạm vi:

- authentication/authorization
- upload file multipart
- artifact content retrieval
- review history listing
- pagination/search
- custom OpenAPI beyond FastAPI defaults

## Design Choice

Chọn `FastAPI + service layer nhỏ`.

Lý do:

- đủ nhẹ cho bản API tối thiểu
- route handlers giữ mỏng, không trộn logic HTTP với Temporal client calls
- dễ test từng lớp: models, service, routes
- không cần đụng sâu vào orchestration code đã có

## Architecture

Thêm 4 module mới:

- `doc_agents/api.py`
  - tạo `FastAPI()` app
  - khai báo 6 routes
  - map request/response HTTP sang service layer
- `doc_agents/api_models.py`
  - chứa request/response models của HTTP API
  - giữ tách biệt khỏi Temporal workflow payloads
- `doc_agents/api_service.py`
  - chứa `WorkflowApiService`
  - chịu trách nhiệm connect Temporal, build workflow handle, start/query/signal workflow
- `doc_agents/api_settings.py`
  - đọc config API và Temporal từ environment

Không thay đổi workflow state model để chứa payload lớn. API chỉ trả metadata nhỏ như status, next actions, artifact versions, workflow id.

`main.py` sẽ đổi từ demo print sang entrypoint khởi tạo app FastAPI để chạy bằng Uvicorn.

## API Contracts

### POST /workflows/start

Request:

```json
{
  "document_id": "doc-123",
  "source_uri": "file:///path/to/source.docx",
  "enable_vision": false,
  "task_queue": "doc-agents"
}
```

Response:

```json
{
  "workflow_id": "document-workflow-doc-123",
  "document_id": "doc-123",
  "status": "started"
}
```

Notes:

- `task_queue` là optional, default lấy từ config
- API chỉ start workflow, không chờ completion

### GET /workflows/{document_id}/status

Response:

```json
{
  "document_id": "doc-123",
  "workflow_id": "document-workflow-doc-123",
  "status": "waiting_for_ir_review"
}
```

### GET /workflows/{document_id}/snapshot

Response:

```json
{
  "document_id": "doc-123",
  "workflow_id": "document-workflow-doc-123",
  "status": "waiting_for_final_review",
  "next_actions": ["rerun:synthesis"],
  "artifact_versions": {
    "semantic_chunks": 1,
    "data_schema_json": 2,
    "business_rules_json": 1,
    "workflows_json": 1,
    "markdown_draft": 3
  }
}
```

### POST /workflows/{document_id}/reviews/ir

Request:

```json
{
  "action": "approve",
  "comment": "IR looks good",
  "targets": []
}
```

hoặc:

```json
{
  "action": "reject",
  "comment": "Missing business rules",
  "targets": ["business_rules"]
}
```

Response:

```json
{
  "document_id": "doc-123",
  "accepted": true,
  "signal": "ir_review_submitted"
}
```

### POST /workflows/{document_id}/reviews/final

Request:

```json
{
  "action": "reject",
  "comment": "Please fix markdown formatting",
  "targets": ["markdown_draft"]
}
```

Response:

```json
{
  "document_id": "doc-123",
  "accepted": true,
  "signal": "final_review_submitted"
}
```

### POST /workflows/{document_id}/artifacts/ir-update

Request:

```json
{
  "target": "data_schema",
  "artifact_id": "doc-123-data_schema_json-v2",
  "artifact_type": "data_schema_json",
  "version": 2,
  "uri": "s3://doc-artifacts/doc-123/data_schema_json/v2/doc-123-data_schema_json-v2.bin"
}
```

Response:

```json
{
  "document_id": "doc-123",
  "accepted": true,
  "signal": "ir_artifact_updated"
}
```

## Validation Rules

- `document_id` từ path map sang workflow id nội bộ: `document-workflow-{document_id}`
- `action` chỉ nhận `approve`, `reject`, `comment`
- `targets` phải map được sang `ReviewTarget`
- `artifact_type` phải khớp `target`
  - `data_schema` -> `data_schema_json`
  - `business_rules` -> `business_rules_json`
  - `workflows` -> `workflows_json`

## Error Handling

Trả lỗi tối thiểu nhưng rõ ràng:

- `400` khi payload hợp lệ về shape nhưng sai business rule, ví dụ `artifact_type` không khớp `target`
- `404` khi workflow không tồn tại
- `409` khi start workflow bị trùng `document_id`
- `503` khi Temporal unavailable
- `422` cho schema validation errors của FastAPI/Pydantic

Không trả `200` nếu signal/query/start không thực sự được Temporal chấp nhận.

## Code Boundaries

### HTTP layer

Route handlers chỉ nên:

- nhận Pydantic request
- gọi `WorkflowApiService`
- trả Pydantic response
- map exceptions thành HTTP errors

### Service layer

`WorkflowApiService` chịu trách nhiệm:

- mở Temporal client theo settings
- start workflow bằng `WorkflowStartInput`
- build workflow handle từ `document_id`
- query `current_status` và `snapshot`
- signal `ReviewSubmission`
- signal `ArtifactReviewUpdatePayload`

### Workflow layer

Workflow hiện có chỉ cần giữ nguyên contract:

- run với `WorkflowStartInput`
- query `current_status`
- query `snapshot`
- signal `submit_ir_review`
- signal `submit_final_review`
- signal `submit_ir_artifact_update`

Không thêm HTTP concerns vào workflow code.

## Testing Strategy

### 1. API model tests

Kiểm tra:

- payload schema hợp lệ
- `artifact_type` khớp `target`
- response models serialize đúng fields dự kiến

### 2. Service tests

Mock Temporal client/handle để kiểm tra:

- workflow id đúng theo `document_id`
- query đúng method
- signal đúng payload và method
- start workflow dùng đúng task queue

### 3. FastAPI route tests

Dùng `TestClient`, patch dependency/service để kiểm tra:

- status code đúng
- body response đúng
- lỗi `404`, `409`, `503` được map đúng

Không cần integration test Temporal thật cho vòng API đầu tiên, vì workflow core đã có integration tests riêng.

## Execution Plan Preview

Implementation nên đi theo thứ tự:

1. thêm dependencies FastAPI/Uvicorn/Pydantic trong `requirements.txt`
2. viết tests đỏ cho API models và service
3. implement settings/models/service
4. viết tests đỏ cho routes
5. implement FastAPI app và `main.py`
6. chạy full suite

## Risks

- Nếu route handlers nói chuyện trực tiếp với Temporal khắp nơi, code sẽ khó test và khó mở rộng
- Nếu API trả artifact payload lớn, nó sẽ phá nguyên tắc state/payload nhỏ của hệ thống
- Nếu cho phép `artifact_type` không khớp `target`, review update path sẽ tạo state không nhất quán

## Success Criteria

API được coi là đạt bản đầu khi:

- có đủ 6 endpoints đã chốt
- start/query/review/update chạy qua Temporal contracts hiện có
- response chỉ chứa metadata nhỏ
- tests cho models, service, và routes đều pass
