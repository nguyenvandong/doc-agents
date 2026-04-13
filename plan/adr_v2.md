# ADR v2: Temporal-Native Orchestration for BRD/SRS to Markdown Spec Pipeline

## Status

Proposed

## Date

2026-04-12

## Context

Hệ thống cần chuyển đổi tài liệu BRD/SRS dạng `.docx` thành Markdown có cấu trúc chuẩn để làm đầu vào cho các agent khác.

Bản blueprint ban đầu trong [adr.md](/E:/workspace/doc-agents/plan/adr.md) mô tả hệ thống như một `multi-agent pipeline` gồm 4 phase:

1. Ingestion và parsing
2. Specialized extraction bởi các specialist agents
3. Synthesis thành Markdown
4. Validation và feedback loop

Sau khi làm rõ bài toán, các ưu tiên kiến trúc thực tế được xác định là:

1. `Human-in-the-loop` là ưu tiên cao nhất
2. Workflow phải có `durability`, `resume`, và không mất tiến trình khi worker/process chết
3. Song song hóa chỉ là ưu tiên sau cùng

Ngoài ra, hệ thống cần hỗ trợ hai kiểu tương tác người dùng:

1. Reviewer duyệt hoặc sửa JSON trung gian trước khi tiếp tục
2. Reviewer comment trên Markdown draft/final và yêu cầu hệ thống loop lại

Thời gian chờ reviewer là không đoán trước được, có thể kéo dài rất lâu. Điều này khiến bài toán không còn là batch pipeline ngắn hạn, mà là một workflow dài hạn có trạng thái, artifact trung gian, và nhiều điểm chờ duyệt thủ công.

## Problem Statement

Ta cần một orchestration model cho phép:

- Quản lý vòng đời của một lần xử lý tài liệu như một thực thể có trạng thái rõ ràng
- Pause và resume đáng tin cậy sau thời gian chờ rất dài
- Giữ audit trail cho các bước chạy, artifacts, quyết định duyệt, và comment
- Retry đúng ở mức external operation thay vì rerun toàn bộ pipeline
- Loop lại có chọn lọc khi reviewer yêu cầu sửa một phần
- Self-host được

## Decision

Chọn `Temporal` làm orchestration layer trung tâm cho hệ thống.

Hệ thống sẽ được thiết kế theo hướng `durable document workflow`, không theo hướng `multi-agent fan-out` là primitive chính.

Primitive kiến trúc chính sẽ là:

- `Workflow`: đại diện cho vòng đời xử lý của một tài liệu
- `Activities`: các bước thực thi có thể lỗi, có thể retry, có side effect
- `Persisted artifacts`: chunks, JSON IR, Markdown draft, validation issues, review decisions
- `Review gates`: các điểm chờ con người duyệt/sửa trước khi workflow tiếp tục
- `Signals`, `Updates`, `Queries`: cơ chế giao tiếp với workflow đang chạy

## Why Temporal

Temporal phù hợp với bài toán này vì:

- Temporal được thiết kế cho workflow dài hạn, có thể resume sau crash, network failure, hoặc hạ tầng gián đoạn, kể cả sau thời gian rất dài. Tài liệu chính thức mô tả workflow có thể tiếp tục chạy trong nhiều ngày hoặc nhiều năm mà vẫn khôi phục đúng trạng thái trước đó ([Temporal Workflow](https://docs.temporal.io/workflows)).
- Workflow trong Temporal là nơi orchestration diễn ra; các tác vụ có thể lỗi hoặc có side effect nên được đặt vào Activities, là primitive phù hợp cho parse file, gọi LLM, render Markdown, đọc/ghi storage, và indexing ([Activities](https://docs.temporal.io/activities)).
- Temporal hỗ trợ message passing trực tiếp tới workflow đang chạy bằng `Signals`, `Updates`, và `Queries`, rất phù hợp cho use case reviewer approve/reject/comment trên artifact trung gian hoặc output cuối ([Python message passing](https://docs.temporal.io/develop/python/workflows/message-passing)).
- Temporal mặc định retry Activities thay vì retry cả Workflow. Điều này khớp với pipeline tài liệu: lỗi thường nằm ở external calls hoặc side effects, không nên rerun toàn bộ orchestration ([Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies)).
- Temporal có thể self-host. Tài liệu chính thức nêu rõ có thể self-host Temporal Service hoặc dùng Temporal Cloud ([Temporal Docs Home](https://docs.temporal.io/)).

## Rejected Alternatives

### 1. Custom DB + Queue + State Machine

Ưu điểm:

- Dễ self-host
- Ít hạ tầng hơn trong giai đoạn đầu
- Phù hợp nếu pipeline ngắn và ít trạng thái

Nhược điểm:

- Toàn bộ pause/resume dài hạn, retry orchestration, dedup message, timeout logic, audit trail, và selective rerun phải tự xây
- Human review gate trở thành logic ứng dụng custom dễ phân tán và mục nát theo thời gian
- Rủi ro kiến trúc cao hơn khi nhu cầu long-running workflow tăng

Kết luận: không phù hợp với ưu tiên `human-in-the-loop` và `durability` là trọng tâm.

### 2. BPMN/Process Engine nặng hơn

Ưu điểm:

- Mạnh về approval/task flow kiểu nghiệp vụ
- Phù hợp nếu cần BPMN, form task, hoặc quy trình nghiệp vụ có nhiều vai trò người dùng

Nhược điểm:

- Quá nặng ceremony cho một pipeline code-first, LLM-centric, document-centric
- JSON IR loop, selective rerun, và integration với extraction code kém tự nhiên hơn

Kết luận: có thể dùng nếu tương lai bài toán trở thành business process orchestration thuần nghiệp vụ, nhưng hiện tại không phải lựa chọn tối ưu.

## Architectural Reframing

ADR cũ nên được viết lại theo trục mới:

- Từ: `multi-agent pipeline`
- Thành: `durable document workflow`

Điều này không phủ nhận 4 phase cũ, nhưng thay đổi primitive và cách mô tả:

- Phase 1 trở thành `artifact preparation`
- Phase 2 trở thành `orchestrated extraction activities`
- Phase 3 trở thành `synthesis from persisted IR`
- Phase 4 trở thành `validation and review loop inside the same long-running workflow`

Khái niệm `agent` chỉ nên là implementation detail của extraction logic, không phải primitive chính trong ADR.

## Temporal-Native Mapping

### 1. Workflow Identity

Mỗi lần xử lý một tài liệu sẽ có một `Document Workflow Execution`.

Workflow phải có:

- `workflow_id` ổn định theo document run
- metadata đầu vào: document id, file location, submitter, processing options, version của prompt/template
- state nhỏ, đủ để điều hướng flow

Workflow không nên giữ toàn bộ:

- raw `.docx`
- toàn bộ chunk payload lớn
- JSON IR lớn
- Markdown draft lớn

Thay vào đó, workflow chỉ giữ:

- artifact references
- trạng thái phase hiện tại
- summary metadata
- pending review state

### 2. Persisted Artifacts

Artifacts nên được lưu ngoài workflow history, ví dụ trong object storage hoặc database.

Tối thiểu cần các loại artifact sau:

- `source_document`
- `parsed_document`
- `semantic_chunks`
- `data_schema_json`
- `business_rules_json`
- `workflows_json`
- `markdown_draft`
- `validation_report`
- `review_decisions`
- `review_comments`

Mỗi artifact nên có:

- artifact id
- workflow id
- artifact type
- version
- created_at
- created_by
- source references

### 3. Phase 1: Ingestion and Parsing

Map sang Activities:

- `store_source_document`
- `parse_docx_activity`
- `extract_tables_activity`
- `semantic_chunk_activity`
- `vision_extract_activity` nếu bật tùy chọn

Kết quả của phase này là một `chunk set` có version, đủ để downstream extraction đọc lại độc lập.

Guideline:

- Mỗi step có side effect hoặc phụ thuộc thư viện ngoài phải là Activity
- Nếu parsing hoặc OCR có thể chạy lâu, vẫn để ở Activity chứ không làm trong Workflow
- Nếu parse thất bại vì input không hợp lệ, Activity nên surface lỗi non-retryable

### 4. Phase 2: Specialized Extraction

Map sang các Activities độc lập:

- `extract_data_schema_activity`
- `extract_business_rules_activity`
- `extract_workflows_activity`

Các activity này có thể chạy song song nếu input chunk set đã sẵn sàng.

Đầu ra là các artifact IR có version:

- `data_schema_json`
- `business_rules_json`
- `workflows_json`

Quan trọng:

- Từ góc nhìn Temporal, đây vẫn là `activities orchestrated by one workflow`, không cần biến từng extractor thành child workflow từ đầu
- Nếu cần specialist prompts hoặc model khác nhau, đó là configuration của activity, không phải lý do để tách workflow

### 5. Review Gate A: Human Review on IR

Sau khi extraction xong, workflow chuyển sang trạng thái:

- `WAITING_FOR_IR_REVIEW`

Reviewer có thể:

- approve toàn bộ IR
- sửa một hoặc nhiều artifact JSON
- reject và yêu cầu rerun một extractor cụ thể

Temporal mapping:

- `Signal` phù hợp cho tác vụ gửi lệnh bất đồng bộ như approve/reject/comment
- `Update` phù hợp nếu caller cần phản hồi đồng bộ, ví dụ hệ thống UI muốn biết request sửa có được chấp nhận hay không
- `Query` dùng để đọc trạng thái hiện tại, ví dụ workflow đang chờ gì, artifact version hiện tại là gì

Workflow sẽ dùng cơ chế chờ điều kiện để đứng lại cho tới khi có quyết định review tương ứng. Message handlers phải cập nhật state review thay vì gọi trực tiếp business logic bên ngoài. Temporal hỗ trợ `wait_condition` và pattern chờ handler hoàn tất trước khi workflow kết thúc hoặc Continue-As-New ([Python message passing](https://docs.temporal.io/develop/python/workflows/message-passing), [Continue-As-New - Python SDK](https://docs.temporal.io/develop/python/workflows/continue-as-new)).

### 6. Phase 3: Synthesis

Sau khi IR được duyệt, workflow gọi:

- `synthesize_markdown_activity`
- `render_mermaid_activity`
- `generate_frontmatter_activity`
- `persist_markdown_activity`

Kết quả là `markdown_draft` version mới.

Nếu cần deterministic output hơn, synthesis nên dựa tối đa trên IR đã persisted thay vì gọi lại extraction logic.

### 7. Phase 4: Validation

Validator nên là Activity:

- `validate_markdown_against_chunks_activity`

Input:

- current markdown draft
- approved IR
- source chunks

Output:

- `validation_report`
- danh sách `issues`
- severity và source mapping

Nếu validator pass:

- workflow chuyển sang `WAITING_FOR_FINAL_REVIEW` hoặc `COMPLETED`, tùy sản phẩm có bắt buộc review cuối hay không

Nếu validator fail:

- workflow quyết định selective rerun

### 8. Review Gate B: Human Review on Markdown

Sau khi có `markdown_draft`, reviewer có thể:

- approve draft
- comment trực tiếp trên output
- yêu cầu sửa một phần cụ thể

Workflow phải chuyển comment thành instruction có cấu trúc:

- comment nhắm tới `data_schema`
- comment nhắm tới `business_rules`
- comment nhắm tới `workflow steps`
- comment chỉ nhắm tới formatting/synthesis

Mục tiêu là chỉ rerun phần cần thiết:

- comment vào business rules thì rerun extractor tương ứng rồi synthesize lại
- comment vào formatting thì chỉ rerun synthesis

## Selective Re-run Strategy

Workflow cần có routing logic rõ ràng:

- `issue.category = extraction.data_schema` -> rerun data schema extraction
- `issue.category = extraction.business_rules` -> rerun business rules extraction
- `issue.category = extraction.workflows` -> rerun workflow extraction
- `issue.category = synthesis.formatting` -> rerun synthesis only
- `issue.category = parse.source_loss` -> quay lại parsing/chunking

Selective rerun là logic của Workflow, không phải logic UI.

## Retry and Failure Handling

### Principle

Retry ở mức `Activity`, không retry nguyên `Workflow`.

Theo Temporal docs:

- Activities được retry mặc định
- Workflows không retry mặc định và thường không nên retry toàn bộ ([Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies))

### Apply to this system

Nên retry:

- network call tới model provider
- object storage read/write lỗi tạm thời
- transient parser failures do môi trường
- validator phụ thuộc external service bị timeout

Không nên retry vô hạn:

- input file hỏng
- JSON reviewer sửa sai schema
- prompt/output không hợp lệ về mặt nghiệp vụ mà cần con người can thiệp

Các lỗi kiểu này nên được đánh dấu non-retryable để workflow chuyển sang trạng thái cần xử lý thủ công.

## Child Workflow Decision

Không dùng Child Workflows trong phiên bản đầu tiên chỉ để "tổ chức code".

Temporal docs khuyến nghị bắt đầu từ một workflow đơn nếu workload còn bounded, và chỉ dùng Child Workflows khi có nhu cầu rõ ràng như chia nhỏ workload lớn hoặc tách service boundary ([Child Workflows](https://docs.temporal.io/child-workflows)).

### Initial rule

Mặc định:

- `1 document = 1 parent workflow`
- parse, extract, synthesize, validate = activities

Chỉ cân nhắc Child Workflow khi có một trong các điều kiện:

- một tài liệu cực lớn khiến event history tăng quá nhanh
- một phase cần tách thành service boundary riêng
- cần fan-out rất lớn vượt ngưỡng một workflow đơn hợp lý

## Continue-As-New Strategy

Vì workflow có thể sống rất lâu và nhận nhiều review messages, thiết kế phải tính tới `Continue-As-New`.

Temporal docs nêu:

- Workflow không bị giới hạn thời gian chạy
- nhưng event history có giới hạn thực tế
- nên dùng Continue-As-New khi history dài hoặc khi workflow nhận nhiều messages ([Event History](https://docs.temporal.io/workflow-execution/event), [Continue-As-New - Python SDK](https://docs.temporal.io/develop/python/workflows/continue-as-new))

### Apply to this system

Nên Continue-As-New khi:

- số lượng review comments/signals tăng cao
- workflow đã qua nhiều vòng rerun
- event history đạt ngưỡng cảnh báo nội bộ

State cần carry sang run mới:

- document id
- current approved artifact references
- current pending review state
- current issue backlog
- version pointers

Không carry theo dữ liệu lớn inline trong workflow state.

### Important caveat

Nếu tương lai dùng Child Workflows, cần lưu ý Child Workflows không tự carry qua Continue-As-New của parent. Vì vậy càng có lý do để phiên bản đầu tránh phụ thuộc vào child workflows khi chưa thực sự cần ([Child Workflows](https://docs.temporal.io/child-workflows)).

## Proposed High-Level Flow

1. Client submit tài liệu
2. Start `DocumentWorkflow`
3. Phase 1 Activities tạo parsed document và chunk set
4. Phase 2 Activities chạy extraction
5. Workflow chuyển sang `WAITING_FOR_IR_REVIEW`
6. Reviewer approve/sửa/reject qua Signal hoặc Update
7. Nếu approved, chạy synthesis
8. Chạy validation
9. Workflow chuyển sang `WAITING_FOR_FINAL_REVIEW`
10. Reviewer approve hoặc comment
11. Workflow route selective rerun nếu cần
12. Khi pass và được duyệt, persist output cuối và complete workflow

## Consequences

### Positive

- Kiến trúc khớp với ưu tiên thực tế: human review và durability
- Pause/resume dài hạn trở thành năng lực mặc định của orchestration layer
- Retry, audit trail, và workflow visibility rõ ràng hơn
- Selective rerun có chỗ đặt logic chuẩn
- Self-host được

### Negative

- Tăng độ phức tạp vận hành do thêm Temporal service
- Team phải học mô hình deterministic workflow và ranh giới workflow/activity
- Nếu lạm dụng message volume hoặc giữ state lớn trong workflow, có thể đụng giới hạn event history

## Non-Goals for v1

- Không tối ưu fan-out cực lớn ngay từ đầu
- Không tách mỗi specialist agent thành một workflow riêng
- Không xây BPMN/task engine đầy đủ
- Không đưa toàn bộ artifact payload lớn vào workflow state

## Open Questions

- Artifact store ban đầu sẽ là gì: Postgres, S3-compatible object storage, hay kết hợp cả hai?
- Review UI sẽ gắn trực tiếp với Temporal client hay đi qua application API trung gian?
- JSON IR schema cụ thể của từng extractor là gì?
- Validator sẽ dựa trên rule-based checks, LLM critic, hay hybrid?
- Mức độ versioning của prompts/templates/artifacts cần chi tiết đến đâu?

## Implementation Guidance for the Next Planning Step

Khi chuyển sang implementation planning, nên bắt đầu từ các khối sau:

1. Workflow contract cho `DocumentWorkflow`
2. Artifact model và storage abstraction
3. Activities cho parse/chunk/extract/synthesize/validate
4. Review API model cho approve, reject, comment, rerun
5. State machine tối thiểu cho workflow
6. Continue-As-New policy và history guardrails

## References

- Temporal Workflow: [https://docs.temporal.io/workflows](https://docs.temporal.io/workflows)
- Activities: [https://docs.temporal.io/activities](https://docs.temporal.io/activities)
- Python message passing: [https://docs.temporal.io/develop/python/workflows/message-passing](https://docs.temporal.io/develop/python/workflows/message-passing)
- Child Workflows: [https://docs.temporal.io/child-workflows](https://docs.temporal.io/child-workflows)
- Event History: [https://docs.temporal.io/workflow-execution/event](https://docs.temporal.io/workflow-execution/event)
- Continue-As-New - Python SDK: [https://docs.temporal.io/develop/python/workflows/continue-as-new](https://docs.temporal.io/develop/python/workflows/continue-as-new)
- Retry Policies: [https://docs.temporal.io/encyclopedia/retry-policies](https://docs.temporal.io/encyclopedia/retry-policies)
