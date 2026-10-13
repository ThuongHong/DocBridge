# Tham khảo cách parse Office cho DocBridge

Ngày kiểm tra: 13/10/2026. Phạm vi: nguồn chính thức và source code của dự án; không benchmark thêm, không gọi API dịch hoặc inference.

## Kết luận áp dụng

Nên tiếp tục hướng đang có: đọc OOXML thành các đoạn có anchor, dịch theo ngữ cảnh, rồi sửa đúng text node trong package gốc. Dùng repo khác để bổ sung cách duyệt cấu trúc và xử lý dependency. Với yêu cầu giữ format Office, chưa có bằng chứng để thay toàn bộ writer bằng một parser xuất Markdown. Đây là nhận định thiết kế từ đối chiếu source bên dưới, không phải bảo đảm mọi file Office đều được hỗ trợ.

Hai mục tiêu cần kiểm chứng riêng: **extract đủ nội dung** và **ghi bản dịch trở lại mà giữ cấu trúc/logic**. Extract thành plain text hoặc Markdown chưa chứng minh được mục tiêu thứ hai.

## Repo và phần đáng học

| Nguồn | Điều đã xác minh | Cách dùng trong DocBridge |
| --- | --- | --- |
| [python-docx](https://github.com/python-openxml/python-docx), [API Paragraph/Run](https://python-docx.readthedocs.io/en/latest/api/text.html) | Gán `Paragraph.text` thay nội dung bằng một run và loại bỏ format ở cấp run. Paragraph có runs lẫn hyperlinks; hyperlinks cũng chứa runs. | Giữ anchor từng nhóm run tương thích, không thay toàn paragraph bằng setter `.text`. Giữ ranh giới hyperlink, field, tab và break. |
| [python-pptx](https://github.com/scanny/python-pptx), [API text](https://python-pptx.readthedocs.io/en/latest/api/text.html) | Gán paragraph text thay toàn nội dung; font có thể kế thừa từ paragraph hoặc slide layout. | Sửa `a:t` có định vị trong run, giữ nguyên các thuộc tính và layout gốc; render để phát hiện chữ tiếng Anh tràn khung. |
| [python-pptx chart source](https://github.com/scanny/python-pptx/blob/master/src/pptx/chart/chart.py) | `Chart.replace_data()` ghi cả XML series và workbook XLSX nhúng. | Nhãn chart và dữ liệu workbook phải đi theo cùng bản dịch/review; chỉ sửa cache là chưa đủ. |
| [Microsoft Open XML SDK](https://github.com/dotnet/Open-XML-SDK) | SDK cung cấp thao tác thấp trên OPC/Open XML; README liệt kê cập nhật cached chart data cùng embedded spreadsheets trong Word/PowerPoint. | Dùng làm nguồn tham chiếu cấu trúc package/relationships/content types; không cần đưa runtime .NET vào app Python chỉ để parse. |
| [openpyxl formula parser](https://openpyxl.readthedocs.io/en/stable/formula.html) | Tokenizer phân biệt literal text với range/function/operator; parsing có giới hạn. `Translator` là chuyển địa chỉ công thức, không phải dịch ngôn ngữ. | Có thể dùng riêng tokenizer để phân loại chuỗi literal; tiếp tục patch XML gốc thay vì load/save workbook. |
| [Unstructured DOCX](https://github.com/Unstructured-IO/unstructured/blob/main/unstructured/partition/docx.py) | Duyệt paragraph và table theo document order, có xử lý nested cells và hyperlink metadata. | Học cách duyệt block để cải thiện Markdown, tránh đọc hết paragraph trước rồi mới đọc table. |
| [Unstructured PPTX](https://github.com/Unstructured-IO/unstructured/blob/main/unstructured/partition/pptx.py), [XLSX](https://github.com/Unstructured-IO/unstructured/blob/main/unstructured/partition/xlsx.py) | PPTX partition loop bỏ chart; XLSX qua pandas thành Table/text và tùy chọn HTML cấu trúc. | Hữu ích cho extraction/Markdown; các output này không cung cấp mapping đủ để dùng thay writer giữ nguyên chart/formula của DocBridge. |
| [Docling](https://github.com/docling-project/docling), [Excel backend](https://github.com/docling-project/docling/blob/main/docling/backend/msexcel_backend.py) | Có mô hình document thống nhất và Markdown/HTML/JSON export. Excel backend mở workbook với `data_only=True`. | Tham khảo tầng document→Markdown; Excel extraction theo cache không đủ để chứng minh logic công thức sau dịch. |
| [Apache POI formula evaluation](https://poi.apache.org/components/spreadsheet/eval.html) | Công thức có cached result. Khi đổi input/formula, giá trị cache có thể vẫn cũ nếu chưa evaluate/recalculate. | Kiểm chứng bằng engine tính lại thật; không lấy cached result nguyên vẹn làm bằng chứng giữ ngữ nghĩa. |

## Điểm cần sửa ngay ở Excel

Microsoft xác định SUMIF chọn cell theo criteria; criteria có thể là text, reference hoặc function. `*` và `?` là wildcard; `~` dùng escape. Vì vậy khi A1 đổi từ `控制器` thành `Controller`, `SUMIF(A1:A2,"控制器",B1:B2)` không còn chọn cùng cell sau khi tính lại. Đây là suy luận trực tiếp từ semantics SUMIF và tình huống đang kiểm thử trong DocBridge. [Microsoft SUMIF](https://support.microsoft.com/en-au/excel/functions/sumif-function)

Đề xuất fix hẹp, có thể kiểm chứng:

1. Nhận diện criteria literal của SUMIF/COUNTIF và các biến thể nhiều criteria, gắn nó với range trực tiếp mà công thức sử dụng. Chỉ đồng bộ khi mapping source→reviewed target trong range là rõ ràng. Cùng source nhưng nhiều target khác nhau phải báo mâu thuẫn, không lấy target đầu tiên.
2. Giữ function, toán tử, địa chỉ, số và các string dùng làm code/đường dẫn/format. Không dịch mọi chuỗi trong dấu ngoặc kép: đó có thể là tham số INDIRECT, HYPERLINK hoặc TEXT, không phải nhãn người đọc.
3. Với criteria có wildcard, biểu thức so sánh, named range, external reference hoặc dạng chưa hỗ trợ, giữ giới hạn rõ ràng và không tự suy diễn. Target mới có `*`, `?`, `~` cũng cần xử lý escape hoặc từ chối mapping không an toàn. Cơ sở cho giới hạn này là syntax criteria Microsoft mô tả; đây là chính sách đề xuất cho app. [Microsoft SUMIF](https://support.microsoft.com/en-au/excel/functions/sumif-function)
4. Dùng tokenizer để xác định token; patch đúng vị trí literal trong công thức gốc. Không nối token lại một cách vô điều kiện: tài liệu nói token whitespace luôn là một space dù source có nhiều space. `RANGE` cũng có thể là defined name, nên nhận token RANGE chưa có nghĩa đã giải được địa chỉ cell. [openpyxl parsing formulas](https://openpyxl.readthedocs.io/en/stable/formula.html)
5. Kiểm tra trước/sau bằng LibreOffice tính lại, gồm criteria, công thức số và kết quả. Đây là đề xuất kiểm chứng theo cảnh báo cache từ POI, không phải tích hợp Java vào app. [Apache POI formula evaluation](https://poi.apache.org/components/spreadsheet/eval.html)

`openpyxl.load_workbook()/save()` không nên thay writer hiện tại: tài liệu cảnh báo shape có thể mất khi mở rồi lưu, rich text mặc định không được giữ, và `data_only` đọc giá trị đã cache. Dùng tokenizer độc lập tránh phải dựng lại package qua object model này. [openpyxl tutorial](https://openpyxl.readthedocs.io/en/stable/tutorial.html)

## Đối chiếu implementation hiện có

Đã đọc `src/converter/office.py` và `src/converter/office_drawings.py` trong workspace:

- Reader nhóm text nodes theo run properties và ranh giới cấu trúc; anchor lưu part/path hoặc worksheet/cell/text index. Writer sửa package gốc, giữ byte của các part không thay. Hướng này phù hợp yêu cầu giữ format.
- Shared string được clone theo cell khi dịch, tránh một reviewed target vô tình đổi mọi cell dùng chung string.
- Chart đã có binding từ cache đến cell/embedded workbook; phù hợp mẫu cập nhật đồng thời trong python-pptx/Microsoft SDK.
- Tại thời điểm khảo sát, formula cell được đọc thành literal và không có translation segment; writer giữ nguyên công thức. Đây là khoảng trống của trường hợp SUMIF/COUNTIF, không phải lỗi cần thay cả parser.

Các nhận xét trên là quan sát code local, không phải kết quả test mới. Nghiên cứu này chưa xác nhận native SmartArt regeneration, công thức tổng quát hoặc mọi tính năng Office. Không đề xuất thêm framework parsing nặng vào bản build hiện tại.

## Áp dụng sau nghiên cứu

`excel_formulas.py` đã được thêm để đồng bộ criteria literal ở vùng ô/cột trực tiếp cho SUMIF/COUNTIF/AVERAGEIF và các biến thể IFS. Writer dùng tokenizer riêng và thay span trong chuỗi gốc; không mở/lưu workbook qua openpyxl. Trường hợp ambiguous/collision hoặc target tạo wildcard bị từ chối trước khi ghi output. Các dạng chưa hỗ trợ giữ nguyên và có warning khi reader thấy chữ Trung trong formula.

Test thực tế với nhãn do Argos dịch, network bị chặn: LibreOffice tính lại control chưa sửa ra `0, 0`, file đã sửa ra `12, 1`; công thức số vẫn ra `24`. Source và result đều một trang, đã kiểm tra ảnh render. Chi tiết nằm tại `docs/DOCBRIDGE_VALIDATION.md` và `.test-data/excel-formulas/report.json`. Đây là bằng chứng local cho fixture này, không mở rộng thành tuyên bố đã giữ ngữ nghĩa mọi công thức.
