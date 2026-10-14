# DocBridge và các công cụ xử lý tài liệu hiện có

Kiểm tra nguồn chính thức ngày 13/10/2026. DocBridge đối chiếu tại `2103fcc`. Đây là so sánh thiết kế và tính năng được công bố; chưa chạy cùng tài liệu qua các engine bên ngoài, nên không xếp hạng chất lượng hay tốc độ.

## Khác nhau ở đầu ra

| Công cụ | Công việc chính | Quan hệ với DocBridge |
| --- | --- | --- |
| DocBridge | Dịch DOCX/XLSX/PPTX bằng sửa text trong package gốc; PDF có text/scan → Markdown hoặc Word tái tạo; Argos offline hoặc API tương thích OpenAI | Ứng dụng desktop tích hợp, đã có checkpoint và glossary; PDF còn đơn giản |
| PDFMathTranslate / PDFMathTranslate-next + BabelDOC | Dịch PDF, xuất PDF đơn ngữ/song ngữ có bố cục | Đối chứng trực tiếp khi cần **PDF dịch vẫn là PDF** |
| MinerU | Parse PDF/scan/Office thành nội dung có cấu trúc; có nhiều renderer | Ứng viên thay tầng parse PDF |
| Docling | Parse đa định dạng thành DoclingDocument, Markdown/JSON/HTML… | Ứng viên tầng parse và chuẩn hóa dữ liệu |
| Marker | Chuyển tài liệu thành Markdown/JSON/HTML/chunks; OCR và LLM tùy chọn | Đối chứng cho sách/scan → nội dung để dịch |
| Okapi / OmegaT | Filter Office, inline tags và luồng dịch CAT | Đối chứng cho Office roundtrip, không thay trực tiếp parser sách PDF |

Nguồn: [PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate), [PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next), [MinerU](https://github.com/opendatalab/MinerU), [Docling formats](https://docling-project.github.io/docling/usage/supported_formats/), [Marker](https://github.com/datalab-to/marker), [nghiên cứu Office đã có](OFFICE_TRANSLATION_RESEARCH.md).

**Parse đúng cấu trúc, dịch đúng nghĩa và dựng lại bố cục là ba phép kiểm chứng riêng.** Có Markdown tốt chưa chứng minh xuất lại PDF giống gốc; hỗ trợ đọc XLSX chưa chứng minh ghi lại workbook mà giữ công thức và styles.

## PDF tài liệu và sách

**BabelDOC/PDFMathTranslate-next** phù hợp nhất về mặt chức năng nếu mục tiêu là PDF dịch giữ bố cục: có PDF đơn ngữ/song ngữ, chia tài liệu dài rồi ghép, glossary và endpoint OpenAI-compatible, kể cả local server. Tuy nhiên README BabelDOC vẫn ghi trọng tâm Anh → Trung; tiếng Anh đích mới được mô tả là hỗ trợ cơ bản. Dịch text trong bảng là tùy chọn thử nghiệm, mặc định tắt; OCR workaround giả định chữ đen nền trắng. Vì vậy không thể suy từ demo Anh → Trung sang bảo đảm sách Trung → Anh hoặc mọi bản scan. API BabelDOC trực tiếp được đánh dấu nội bộ; upstream khuyến nghị API cấp cao của pdf2zh-next. [BabelDOC README](https://github.com/funstory-ai/BabelDOC).

**MinerU 4.0** có parse scan, bố cục, bảng/công thức và chia việc đọc theo trang/block; đáng đưa vào đối chứng sách kỹ thuật. Lưu ý tích hợp sách: `mineru parse` mặc định mười trang đầu, còn `mineru-kit parse` mặc định toàn tài liệu. [MinerU README](https://github.com/opendatalab/MinerU).

Không còn chính xác nếu gọi MinerU là “chỉ xuất Markdown”: có renderer DOCX/PDF/EPUB bên cạnh Markdown/HTML và dữ liệu cấu trúc; từng CLI/API chỉ mở một phần. PDF renderer phân biệt giữ geometry và reflow, còn Office mặc định reflow. Đây là dựng từ kết quả parse, chưa phải bằng chứng giữ nguyên Office package. [Output contract](https://opendatalab.github.io/MinerU/reference/output_files/).

**Docling** có nhận diện thứ tự đọc, bảng, OCR, công thức và biểu diễn thống nhất. Phù hợp hướng PDF → text có cấu trúc → LLM dịch. JSON “lossless” là serialization của DoclingDocument; không có nghĩa tái tạo lossless file gốc. Danh sách output hiện tại không phải writer sửa text trong Office/PDF gốc. [Docling](https://github.com/docling-project/docling), [supported formats](https://docling-project.github.io/docling/usage/supported_formats/).

**Marker** có ví dụ sách, xử lý bảng/công thức, bỏ header/footer; LLM tùy chọn hỗ trợ các việc như nối bảng qua trang. Chạy CPU/GPU/MPS, nhưng cần model cục bộ; mode dùng LLM còn phụ thuộc model/endpoint được chọn. Đây là lựa chọn parse đáng thử, không tự tạo một bản PDF đã dịch giống trang gốc. Các benchmark trong README là kết quả upstream, chưa phải phép so với DocBridge trên file của chúng ta. [Marker README](https://github.com/datalab-to/marker/blob/master/README.md).

## Cài đặt và license

| Công cụ | Điểm cần tính khi đưa vào bản công ty |
| --- | --- |
| PDFMathTranslate-next / BabelDOC | Code AGPL-3.0; thêm assets/model/font và một dịch vụ/model dịch. Việc có assets offline không tự cung cấp model dịch offline. |
| Docling | Code MIT; model phụ thuộc có license riêng. Pipeline local có thể chạy không gửi tài liệu ra ngoài; remote services phải cấu hình bật. |
| MinerU | License hiện tại dựa Apache-2.0 **kèm điều khoản bổ sung**, gồm ngưỡng thương mại và attribution cho dịch vụ online. Không gọi đơn giản là Apache-2.0 thuần. |
| Marker | Code hiện tại Apache-2.0; weights dùng license riêng có điều kiện. README nêu miễn phí cho nghiên cứu, cá nhân và startup dưới ngưỡng 5 triệu USD funding/revenue. |

Nguồn license và triển khai: [pdf2zh-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next), [BabelDOC license](https://github.com/funstory-ai/BabelDOC/blob/main/LICENSE), [Docling license/model note](https://github.com/docling-project/docling#license), [Docling remote options](https://docling-project.github.io/docling/usage/advanced_options/), [MinerU license](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md), [Marker code license](https://github.com/datalab-to/marker/blob/master/LICENSE), [Marker model license](https://github.com/datalab-to/marker/blob/master/MODEL_LICENSE). Đây là ghi nhận điều khoản upstream, không kết luận pháp lý cho hình thức phân phối cụ thể.

Không nên mặc định các parser này bắt buộc GPU: MinerU hiện có Basic/ONNX chạy CPU; README nêu Standard/ONNX + llama.cpp khoảng 2 GB model, tối thiểu 8 GB RAM. Accelerator và model lớn hơn đổi chi phí cài đặt, RAM và tốc độ. Phải đo trên cấu hình triển khai thực tế. [MinerU hardware table](https://github.com/opendatalab/MinerU#model-engines-with-extras).

## Vị trí hiện tại và đề xuất

DocBridge có bằng chứng local cho Excel 3 sheet, 39,21 MiB, giữ package và xử lý text thường bị bỏ sót; không phải benchmark 30 MB văn bản Trung duy nhất. PDF mới có mẫu tài liệu ngắn, chưa có bằng chứng sách hàng trăm trang. Không dùng số test pass để suy ra chất lượng parse hoặc dịch mọi tài liệu. [Excel report](LARGE_XLSX_REPRO.md), [validation](DOCBRIDGE_VALIDATION.md).

Đề xuất kỹ thuật:

1. Giữ UI, job/checkpoint, glossary và Office writer hiện có. Đối chứng Okapi trước khi thay Office engine.
2. Với **PDF → Markdown/Word để dịch**, prototype Docling trước cho tầng parse chuẩn hóa; dùng MinerU đối chứng trên cùng sách Trung. Chọn dựa coverage, thứ tự đọc, bảng, RAM/thời gian và license triển khai, không coi thứ tự thử là xếp hạng chất lượng.
3. Với **PDF → PDF dịch giữ trang**, prototype pdf2zh-next/BabelDOC riêng; kiểm tra đặc biệt chiều Trung → Anh và text trong bảng.
4. Dùng Marker làm phương án đối chứng bổ sung nếu điều kiện model phù hợp. Chưa có cơ sở fork toàn bộ app nào.

Trước quyết định, cần cùng bộ tài liệu một cột, hai cột, bảng qua trang, scan và sách dài; đo text bị thiếu/lặp, sai thứ tự, bảng/công thức, độ tràn chữ sau dịch, thời gian/RAM, pause/resume. Dùng cùng model dịch để tách ảnh hưởng parser khỏi chất lượng ngôn ngữ. Đây là kế hoạch đối chứng, chưa được thực hiện trong lượt nghiên cứu này.
