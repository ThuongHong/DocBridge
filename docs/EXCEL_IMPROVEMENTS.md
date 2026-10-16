# Cải thiện trích xuất và dịch Excel Trung–Anh

Triển khai bởi **GPT-6.1 Sol, reasoning medium**, kiểm tra độc lập bằng các workbook thật trong [CHINESE_EXCEL_CORPUS.md](CHINESE_EXCEL_CORPUS.md). Mốc so sánh là commit `db3d610`.

## Vấn đề và thay đổi

Bản cũ đọc đủ 2.228 ô chữ Trung thông thường trong sáu file nhỏ của bộ kiểm tra. Phần còn thiếu nằm ở tên sheet, nội dung phụ và cách xử lý rich text; vì vậy không thể đánh giá độ đầy đủ chỉ bằng việc dịch hết các segment đã tìm thấy.

- Trích xuất tên sheet, chữ trong header/footer in, ghi chú và bình luận. Giữ nguyên mã điều khiển header/footer và tên font.
- Trích xuất từng lựa chọn trong dropdown dạng danh sách hằng. Kiểm tra bản dịch khớp các ô trong vùng validation; chặn dấu phẩy, ký tự điều khiển, danh sách quá 255 ký tự hoặc bản dịch mâu thuẫn. Validation dùng công thức/tham chiếu vẫn giữ dạng công thức.
- Ghép các run rich text liền nhau có cùng toàn bộ thuộc tính định dạng; không đưa phiên âm vào nội dung dịch. Giữ các nhóm khác định dạng riêng biệt.
- Chuẩn hóa tên sheet theo giới hạn Excel, tránh trùng tên; cập nhật tham chiếu cục bộ trong công thức, named ranges, biểu đồ, validation, conditional formatting, liên kết nội bộ và nguồn pivot. Cập nhật cả workbook nhúng trong biểu đồ.
- Tái sử dụng bản dịch theo provider/model/glossary, nguồn, ngữ cảnh và kiểu chữ; mỗi ô vẫn có bản dịch review độc lập. Cache giới hạn và nhận cả nội dung lặp xuất hiện muộn.
- Lập chỉ mục ô khi ghi, tái sử dụng shared strings có kết quả giống nhau, dùng biểu diễn gọn cho sheet lớn/thưa và lưu checkpoint JSON theo luồng.
- Quét lại file xuất, phân loại chữ Hán còn lại và ghi ví dụ vị trí vào `coverage`. Chỉ shared strings thực sự được ô tham chiếu mới được tính là nội dung hiển thị.

## Kiểm tra với dịch Argos thật

Model: `translate-zh_en-1_9.argosmodel`. Chặn kết nối mạng trong tiến trình kiểm tra. Mỗi lần chạy dùng kho job và cấu hình riêng.

| Workbook | Sheet | Ô công thức | Vùng gộp | Ô chữ Trung nguồn | Ô chữ Trung còn lại |
|---|---:|---:|---:|---:|---:|
| Hunan construction costs | 10 | 6 | 99 | 211 | 0 |
| MOF financial reports | 19 | 2 | 78 | 1.099 | 0 |

Tên sheet và chữ header/footer của cả hai file cũng được dịch. Trước sửa, Hunan vẫn còn 10 tên sheet tiếng Trung và một header/footer chứa tiếng Trung dù các ô thông thường đã hết chữ Trung. Sau sửa, bộ quét mở rộng còn thấy các tên cũ trong metadata `docProps/app.xml`; đây không phải tên tab hiển thị trong workbook.

Kiểm tra OOXML độc lập xác nhận địa chỉ ô, style ô, số liệu, biểu thức/thuộc tính công thức, vùng gộp, kích thước và thuộc tính hàng/cột vẫn được giữ. `styles.xml` và các media part được so sánh nguyên byte. SHA-256 file nguồn không đổi.

LibreOffice mở được bản gốc và bản dịch, tính lại cả tám ô công thức với kết quả giống nhau và không có lỗi mới. Hai giá trị MOF là **87** và **14,5**; sáu công thức Hunan đều bằng **0** như bản gốc.

File kiểm tra riêng xác nhận các tham chiếu chéo sheet, vùng 3D, tên sheet có dấu nháy đơn, named range, SUMIF và HYPERLINK nội bộ vẫn cho kết quả đúng sau đổi tên. Chuỗi hằng trong công thức được giữ nguyên.

## Kiểm tra file hơn một triệu ô

OUC procurement budget có 4 sheet, 1.056.681 ô chữ Trung, 65.747 ô công thức và 13 vùng gộp. Dùng nội dung ASCII xác định để kiểm tra đầy đủ đường đọc → gán target → lưu checkpoint → xuất → so sánh cấu trúc. **Đây không phải lần dịch Argos toàn bộ file, cũng không phải đánh giá chất lượng ngôn ngữ.**

Lượt cuối xử lý **1.056.742 segment**: đọc 45,1 giây, lưu checkpoint 41,7 giây, xuất 99,8 giây; tổng cùng các phép đối chiếu là 224,5 giây. Bộ nhớ đỉnh **3.289,8 MiB**; checkpoint khoảng **639 MiB**. Giữ đủ 65.747 ô công thức và 13 vùng gộp. Bộ quét độc lập xác nhận không còn chữ Hán trong các ô văn bản hoặc hai dropdown; chỉ metadata/tác giả còn chữ Hán trong báo cáo xuất.

Kiểm thử cuối: **178 passed, 1 skipped**; Ruff và `git diff --check` đạt. Kết quả chi tiết được ghi trong [EXCEL_IMPROVEMENTS_VALIDATION.json](EXCEL_IMPROVEMENTS_VALIDATION.json).

## Giới hạn đã quan sát

Phần bố cục dưới đây ghi nhận trạng thái tại mốc kiểm tra trích xuất. Chế độ **Dễ đọc** bổ sung sau đó và kết quả xử lý cắt chữ được ghi riêng trong [EXCEL_LAYOUT.md](EXCEL_LAYOUT.md).

- Hunan trước/sau đều xuất thành 21 trang PDF trong LibreOffice. Kiểm tra trực quan trang đầu thấy nhiều câu tiếng Anh bị cắt hoặc xuống dòng vượt chiều cao ô. Writer giữ kích thước gốc, chưa tự giãn hàng/cột. Dịch đầy đủ không đồng nghĩa bản in đã hoàn thiện.
- Argos vẫn có bản dịch thuật ngữ chưa tự nhiên; ví dụ tên liên quan đến “智慧工地” cần review. Kiểm tra không còn chữ Hán chỉ đo độ bao phủ, không chứng minh bản dịch chính xác về nghĩa.
- Tên sheet dài phải rút xuống giới hạn 31 ký tự. Tên tác giả, metadata và mã định dạng có thể còn tiếng Trung và được báo riêng.
- INDIRECT và đích HYPERLINK tính động có thể không đổi tên an toàn; xuất file yêu cầu giữ tên sheet gốc hoặc review/sửa tham chiếu đó. Không tự suy đoán chuỗi tạo tham chiếu lúc chạy.
- Ảnh chưa được OCR trong luồng Excel này. Kết quả công thức được đánh giá lại bởi ứng dụng bảng tính; không dịch tùy tiện mọi chuỗi trong công thức.
- File triệu ô vẫn tốn vài GB RAM và hàng trăm MB checkpoint. Bài stress không chứng minh UI review một triệu hàng hay quá trình dịch/checkpoint nhiều batch đã tối ưu.

## Chạy lại

Từ thư mục repository; yêu cầu môi trường `.venv` có extras `offline` và `dev`, model Argos đã có trong `assets/models`, cùng bộ file thật trong `.test-data/chinese-excel-corpus`. Các script tạo kết quả trong `.test-data/excel-improvements`.

```bash
PYTHONPATH=src .venv/bin/python scripts/audit-excel-corpus.py .test-data/chinese-excel-corpus --parser-max-chinese-cells 20000 --output .test-data/excel-improvements/parser-audit.json
PYTHONPATH=src .venv/bin/python scripts/validate-excel-translation.py current-hunan .test-data/chinese-excel-corpus/hunan-construction-costs.xlsx
PYTHONPATH=src .venv/bin/python scripts/validate-excel-translation.py current-mof .test-data/chinese-excel-corpus/mof-financial-reports.xlsx
PYTHONPATH=src .venv/bin/python scripts/stress-excel-roundtrip.py
PYTHONPATH=src .venv/bin/python scripts/check-excel-references.py
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests scripts
```

Script `recalculate-excel-corpus.py` dùng `/usr/bin/python3` có UNO và LibreOffice, profile riêng, mở file read-only, chặn macro và cập nhật liên kết. Truyền từng cặp file nguồn/file xuất; script so sánh mọi ô công thức trong cặp. Ví dụ:

```bash
/usr/bin/python3 scripts/recalculate-excel-corpus.py .test-data/excel-improvements/reference-source.xlsx .test-data/excel-improvements/reference-output.xlsx
```

Lần chạy dịch tiếp theo không ghi đè workbook xuất cũ: đường dẫn thực nằm trong `validation.json` của lượt chạy. Lần chạy stress và fixture có tên cố định trong thư mục kiểm tra riêng.
