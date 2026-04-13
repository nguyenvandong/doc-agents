# Document Workflow Handoff Status

## Source Of Truth

Hai file này là nguồn sự thật để hội thoại khác tiếp tục:

- `E:/workspace/doc-agents/plan/implementation_plan_v2.md`
- `E:/workspace/doc-agents/plan/handoff_statuss.md`

Tham chiếu nền kiến trúc:

- `E:/workspace/doc-agents/plan/adr_v2.md`

## Current Status

Ngày cập nhật: `2026-04-12`

Đã hoàn tất trong `implementation_plan_v2.md`:

- [x] Task 1: Add artifact version resolution and next-version writes
- [x] Task 2: Replace extraction scaffolds with real structured outputs from semantic chunks
- [x] Task 3: Persist real frontmatter and Mermaid artifacts during synthesis
- [x] Task 4: Track versioned artifacts through workflow state and reruns
- [x] Task 5: Support review-edited artifact refs and targeted reruns
- [x] Task 6: Strengthen validation against markdown, IR, and chunks
- [x] Task 7: Add storage-backed rerun integration coverage

## What Is Already Implemented

- Temporal Python SDK integration is in place.
- Workflow integration test passes.
- Parser thật dùng `python-docx` + `mammoth`.
- Storage adapter thật dùng Postgres + MinIO.
- Repository có:
  - `store_bytes(...)`
  - `load_bytes(...)`
  - `load_latest(...)`
  - version auto-increment khi `version=None`
- `parse_docx_activity` parse local `.docx` và persist `parsed_document` nếu env storage được cấu hình.
- `semantic_chunk_activity` đọc `parsed_document` persisted artifact và persist `semantic_chunks`.
- `extract_data_schema_activity` persist JSON có `fields`.
- `extract_business_rules_activity` persist JSON có `rules`.
- `extract_workflows_activity` persist JSON có `steps`.
- `synthesize_markdown_activity` đọc persisted IR artifacts và persist `markdown_draft`.
- `generate_frontmatter_activity` persist frontmatter YAML.
- `render_mermaid_activity` persist Mermaid text.
- `validate_markdown_against_chunks_activity` validate theo section/category và trả stable issue strings.
- `DocumentWorkflowState` expose `artifact_versions` derived from in-state `ArtifactRef`s.
- `WorkflowSnapshot` expose `artifact_versions`, và Temporal rerun test đã assert `markdown_draft` tăng version sau reject/review loop.
- Review path có thể nhận replacement `ArtifactRef` cho `data_schema_json` / `business_rules_json` / `workflows_json` và đi thẳng sang synthesis.
- Temporal workflow có signal `ir_artifact_updated`; payload vẫn nhỏ và chỉ mang metadata của `ArtifactRef`.
- Validation hiện check theo section `Data Schema`, `Business Rules`, `Workflows` và trả stable issue strings thay vì raw chunk evidence.
- Có module `tests/test_storage_backed_pipeline.py` để assert repository-backed rerun tạo `markdown_draft` version mới và persisted bytes vẫn đọc lại được.

## Important Current Behavior

- Workflow state vẫn chỉ giữ `ArtifactRef`, không mang payload lớn.
- Artifact-producing helpers trong activities đã ghi với `version=None`, nên rerun có thể tạo `v2`, `v3`, ...
- Extraction payload hiện giữ cả:
  - structured keys mới như `fields`, `rules`, `steps`
  - key cũ `evidence`

Lý do: giữ `synthesize_markdown_activity` chưa bị vỡ trước khi Task 6 và các bước sau hoàn tất.

## Next Task

Trạng thái tiếp theo:

- `implementation_plan_v2.md` đã hoàn tất toàn bộ Tasks 1-7.
- Nếu mở hội thoại mới, nên chuyển sang review/cleanup hoặc chuẩn bị PR thay vì tiếp tục implementation plan này.

## Files Most Likely To Change Next

- `E:/workspace/doc-agents/tests/test_storage_backed_pipeline.py`
- `E:/workspace/doc-agents/tests/test_temporal_integration.py`
- `E:/workspace/doc-agents/plan/implementation_plan_v2.md`
- `E:/workspace/doc-agents/plan/handoff_statuss.md`

## Latest Verification

Lệnh verification mới nhất đã chạy:

```powershell
E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Kết quả mới nhất:

- `48 tests`
- `OK`

## Suggested Prompt For Next Conversation

```text
Tiếp tục tại E:\workspace\doc-agents.
Đọc E:\workspace\doc-agents\plan\implementation_plan_v2.md và E:\workspace\doc-agents\plan\handoff_statuss.md trước.
Implementation plan v2 đã xong; giúp review diff, cleanup nếu cần, hoặc chuẩn bị commit/PR. Giữ workflow state chỉ với ArtifactRef.
```

## Notes For The Next Agent

- Không reset hay revert thay đổi hiện có.
- Ưu tiên sửa theo đúng thứ tự trong `implementation_plan_v2.md`.
- Khi claim xong task, nhớ tick lại task đó trong `implementation_plan_v2.md`.
- Sau mỗi task, chạy test targeted trước, rồi chạy full suite.
