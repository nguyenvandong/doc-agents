Dưới đây là bản thiết kế blueprint tổng thể cho hệ thống AI Agentic Pipeline, được cấu trúc theo tiêu chuẩn thiết kế
kiến trúc phần mềm.

# Blueprint Kiến trúc: BRD/SRS to Markdown Spec Pipeline

**Mục tiêu hệ thống:** Tự động hóa quá trình chuyển đổi tài liệu đặc tả nghiệp vụ thô (BRD, SRS dạng Word) thành định
dạng Markdown có cấu trúc chuẩn (Machine-readable), tối ưu để làm đầu vào (context) cho các agent chuyên trách khác (lập
kế hoạch, sinh test case, phân tích mã nguồn).

**Mô hình kiến trúc cốt lõi:** Multi-Agent Collaboration kết hợp Intermediate Representation (Sử dụng JSON làm định dạng
trung gian).

---

## Các Giai đoạn (Phases) và Thành phần (Components) của Pipeline

## Phase 1: Ingestion & Parsing (Tiền xử lý và Phân mảnh)

Nhiệm vụ của giai đoạn này là "làm sạch" và chuẩn hóa dữ liệu đầu vào, bảo toàn tối đa ngữ cảnh của tài liệu gốc trước
khi đưa vào LLM.

* **Document Parser Component:**
    * Chức năng: Đọc file `.docx` thô, bóc tách văn bản và đặc biệt là giữ nguyên vẹn cấu trúc của các bảng biểu (chuyển
      đổi thành dạng text/Markdown table có thể đọc được).
* **Semantic Chunker Component:**
    * Chức năng: Cắt nhỏ tài liệu dựa trên cấu trúc ngữ nghĩa (Heading 1, Heading 2, các section) thay vì cắt mù theo số
      lượng token. Đảm bảo một business rule hoặc một use case không bị gãy đôi.
* **Vision Extractor Component (Optional):**
    * Chức năng: Quét các hình ảnh (BPMN, Flowchart) có trong tài liệu và sử dụng Vision Model để dịch ảnh thành text mô
      tả luồng hoặc mã sơ đồ text-based (Mermaid.js).

## Phase 2: Specialized Extraction (Trích xuất Dữ liệu Chuyên biệt)

Giai đoạn này sử dụng một nhóm "Specialist Agents" xử lý song song. Các agent này không sinh ra Markdown ngay, mà trích
xuất thông tin thành định dạng cấu trúc **JSON** (Intermediate Representation) để triệt tiêu hiện tượng ảo giác (
hallucination).

* **Data Model Agent:**
    * Nhiệm vụ: Quét các thực thể dữ liệu (Entities), thuộc tính, kiểu dữ liệu, định dạng.
    * Đầu ra: `data_schema.json`.
* **Business Rule Agent:**
    * Nhiệm vụ: Trích xuất các logic IF-THEN, ràng buộc hệ thống, validation rules, công thức nghiệp vụ.
    * Đầu ra: `business_rules.json`.
* **Workflow Agent:**
    * Nhiệm vụ: Nhận diện Use cases, luồng đi chuẩn (Happy path), và các luồng ngoại lệ/báo lỗi (Alternate/Exception
      paths).
    * Đầu ra: `workflows.json`.

## Phase 3: Formatting & Synthesis (Tổng hợp và Chuẩn hóa Output)

Giai đoạn này đóng vai trò như một Templating Engine, lắp ráp các mảnh JSON rời rạc thành một tài liệu Markdown hoàn
chỉnh, đạt "chuẩn lập trình".

* **Synthesizer Component:**
    * Chức năng: Map các file JSON từ Phase 2 vào một template Markdown định trước.
* **Markdown Generator Component:**
    * **YAML Frontmatter:** Tạo metadata ở đầu file (Epic, Tags, Status, ID).
    * **Structured Tables:** Kết xuất `data_schema.json` và `business_rules.json` thành các bảng Markdown.
    * **Mermaid.js Renderer:** Chuyển đổi dữ liệu từ `workflows.json` thành các khối code sinh sơ đồ tuần tự (Sequence
      Diagram) hoặc sơ đồ trạng thái (State Diagram) trực quan.

## Phase 4: Validation & Feedback Loop (Kiểm định và Hồi tiếp)

Cơ chế tự phản tỉnh (Self-Reflection) để đảm bảo tính toàn vẹn của dữ liệu đầu ra so với đầu vào.

* **Critic Agent Component (Validator):**
    * Chức năng: Đối chiếu bản Markdown Spec (đầu ra Phase 3) với các Chunks tài liệu gốc (đầu ra Phase 1).
    * Nhiệm vụ: Tìm kiếm các rule bị sót, các mã lỗi bị thiếu, hoặc các logic bị LLM "bịa" thêm.
* **Feedback Router Component:**
    * Chức năng: Nếu Validator phát hiện lỗi, Router sẽ đóng gói các "Issues" này thành prompt và điều hướng luồng chạy
      quay ngược lại Phase 2 (Extraction) để các specialist agents tiến hành bổ sung, cập nhật lại JSON. Nếu pass, xuất
      file `.md` cuối cùng.

---