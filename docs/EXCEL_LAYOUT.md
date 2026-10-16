# Bố cục Excel sau dịch Trung–Anh

Chế độ **Excel → Dễ đọc** xử lý phần văn bản tiếng Anh bị cắt do chiều cao hàng cố định. Đây là bước tiếp theo của [cải thiện trích xuất Excel](EXCEL_IMPROVEMENTS.md), dùng lại bản dịch Argos đã lưu để kiểm tra riêng phần bố cục.

## Thay đổi

- Bật xuống dòng cho ô có bản dịch thay đổi, đo chữ bằng Pillow/FreeType và tăng chiều cao hàng. Ô gộp ngang được đo theo tổng chiều rộng; ô gộp dọc phân bổ chiều cao cho các hàng đang hiển thị.
- Giữ nguyên độ rộng cột, số liệu, công thức, vùng gộp và trạng thái ẩn. Định dạng mới dùng bản sao riêng; các font và cell style gốc không bị sửa.
- Khi chạm mức 409pt mỗi hàng, chữ thuần có thể giảm font từng bước 0,5pt, tối thiểu 9pt. Không tự giảm font trong các rich text run. Trường hợp vẫn không vừa được ghi rõ trong `coverage.layout`.
- Trang có nội dung rộng hơn vùng giấy in được đặt vừa một trang ngang, không ép số trang dọc. Một cột đơn quá rộng dùng tỷ lệ in cụ thể: LibreOffice trong kiểm tra này nhận `fitToWidth=1` nhưng vẫn cắt chữ; tỷ lệ cụ thể khắc phục được ca đó. Phép tính vùng in có tính đến font thay thế rộng hơn.
- Giao diện mặc định **Dễ đọc** và lưu lựa chọn. **Giữ bố cục** giữ kích thước/kiểu gốc. API `write_office(..., excel_layout="preserve")` vẫn mặc định giữ bố cục.

## Bằng chứng lỗi và kiểm tra hồi quy

Với ô gộp có hàng cao 16pt, PDF vẫn chứa chữ của dòng cuối nhưng ảnh không có điểm ảnh chữ ở vị trí đó. Chỉ tăng chiều cao hàng đã đưa số điểm ảnh tối của dòng cuối từ 0 lên 357. Vì vậy kiểm tra không chỉ dựa trên văn bản trích xuất từ PDF.

Lệnh kiểm tra độc lập:

```bash
PYTHONPATH=src .venv/bin/python scripts/validate-excel-layout.py --corpus
```

Năm ca đi qua writer thật rồi mở bằng LibreOffice: gộp ngang, gộp dọc, ô thường, chạm giới hạn chiều cao và một cột quá rộng. Cả năm bản Dễ đọc đều có đủ nội dung khi bỏ khoảng trắng, có điểm ảnh chữ ở dòng cuối và các khung chữ nằm trong chiều rộng giấy. Bản Giữ bố cục tái hiện được lỗi cắt chữ. Ca cột rộng từng thất bại với `text extends beyond paper width` trước khi thêm tỷ lệ in cụ thể.

## Workbook thật

| Workbook | Sheet | Ô chữ được xuống dòng | Hàng tăng chiều cao | Ô giảm font | Trang PDF |
|---|---:|---:|---:|---:|---:|
| Hunan construction costs | 10 | 211 | 76 | 1 | 15 |
| MOF financial reports | 19 | 1.099 | 921 | 0 | 41 |

Cả hai vượt qua đối chiếu địa chỉ ô, số liệu, biểu thức/thuộc tính công thức, vùng gộp, cột, trạng thái hàng, fill, border và number format. Các font và cell style ban đầu vẫn là phần đầu không thay đổi của danh sách sau xuất. Kiểm tra này đối chiếu XML công thức; kết quả tính lại của bản dịch trước thay đổi bố cục được ghi ở báo cáo trích xuất, không được coi là lần tính lại mới của chế độ Dễ đọc.

Trang hướng dẫn Hunan có một ô A1 dài 1.593 ký tự, hàng đã cao 409pt. Font riêng của ô giảm từ 16pt xuống 15pt và tỷ lệ in là 73%. Trang 5 của PDF chứa đủ 991 ký tự không tính khoảng trắng; các khung chữ nằm trong trang. Đã xem ảnh trang hướng dẫn và các trang đầu của hai workbook. Chưa kiểm tra trực quan từng ô trên toàn bộ 56 trang.

File mẫu và ảnh nằm trong `.test-data/excel-layout/`:

- `hunan-construction-costs.en.readable.xlsx`
- `mof-financial-reports.en.readable.xlsx`
- `hunan-instructions.png`, `current-hunan-page1.png`, `current-mof-page1.png`

Kết quả máy đọc được: [EXCEL_LAYOUT_VALIDATION.json](EXCEL_LAYOUT_VALIDATION.json).

Kiểm thử toàn bộ: **190 passed, 1 skipped**. Ruff và `git diff --check` đạt.

## Giới hạn còn lại

Máy Linux kiểm tra dùng Noto Sans thay các font Trung không có sẵn. Đây là ước lượng bằng font hiện có, đã kiểm tra xuất bằng LibreOffice; chưa xác nhận trên Microsoft Excel của Windows. Tỷ lệ in làm giảm kích thước chữ trên giấy, kể cả khi font trong ô vẫn từ 9pt trở lên. Số trang và vị trí ngắt trang có thể thay đổi.

Chữ xoay, căn `fill`, một số định dạng hiển thị tùy biến, vùng gộp dọc quá lớn và rich text vượt chiều cao có chẩn đoán riêng; không tuyên bố tự sửa mọi trường hợp. Bộ kiểm tra hơn một triệu ô trước đó dùng chế độ giữ bố cục, chưa phải đo hiệu năng chế độ Dễ đọc. Thay đổi này cũng không sửa chất lượng ngôn ngữ của bản dịch Argos.
