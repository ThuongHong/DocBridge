# Workbook tiếng Trung thực tế

Đã tải và kiểm kê ngày 16/10/2026. Đây là file XLSX do các cơ quan/trường
đại học công bố, giữ nguyên byte tải về, không phải workbook tự sinh.
File gốc và bộ ZIP nằm trong `.test-data/chinese-excel-corpus/`.
Nguồn tải và SHA-256: [manifest](CHINESE_EXCEL_CORPUS.json).
Kết quả từng sheet: [audit](CHINESE_EXCEL_AUDIT.json).

## Ba mẫu chính

| Workbook | Sheet | Ô công thức | Vùng gộp | Ô chứa tiếng Trung | Chuỗi tiếng Trung khác nhau |
| --- | ---: | ---: | ---: | ---: | ---: |
| `mof-financial-reports.xlsx` | 19 | 2 | 78 | 1.099 | 693 |
| `hunan-construction-costs.xlsx` | 10 | 6 | 99 | 211 | 169 |
| `ouc-procurement-budget.xlsx` | 4 | 65.747 | 13 | 1.056.681 | 7.332 |

- **Biểu tài chính doanh nghiệp tài chính**, Bộ Tài chính Trung Quốc:
  [trang nguồn](https://bgt.mof.gov.cn/zhuantilanmu/rdwyh/czyw/202512/t20251212_3979031.htm).
  Nhiều biểu nghiệp vụ; có 37 ô rich text, các ô số được lưu dưới dạng chuỗi,
  công thức `SUM(B48:B50)` và `B51/6`.
- **Biểu đo chi phí xây dựng**, Sở Nhà ở và Phát triển Đô thị–Nông thôn Hồ Nam:
  [trang nguồn](https://zjt.hunan.gov.cn/hnweb/zxfb/202505/t20250508_33665095.html).
  Sheet hướng dẫn, thông tin dự án, tổng hợp và chi tiết chi phí; các công thức
  SUM nằm trên sáu sheet chi tiết. Có cả tiếng Trung trong header/footer in ấn.
- **Biểu ngân sách tài sản và mua sắm nghiên cứu năm 2027**, Đại học Hải dương
  Trung Quốc: [trang nguồn](https://kjc.ouc.edu.cn/2026/0625/c33319a533142/page.htm).
  Hai sheet nhập liệu và hai sheet dữ liệu nguồn; hai quy tắc data validation,
  34 ô rich text, nhiều công thức nhân/chia. File nén 6.486.342 byte,
  giải nén 91.023.638 byte. Riêng chuỗi `0-无` được điền sẵn **1.048.575 lần**.
  Vì vậy đây là mẫu thử tải lớn và danh mục nghiệp vụ; số ô không tương đương
  hơn một triệu nội dung cần dịch khác nhau.

Nội dung nhãn/hướng dẫn là tiếng Trung; các biểu vẫn chứa số, mã, ký hiệu và
tên hàm Excel. Chưa tìm thấy công thức ô có tham chiếu chéo sheet trong ba mẫu
chính này. Hai mẫu đầu chỉ có ít công thức đơn giản, không đại diện cho mọi
workbook tài chính phức tạp. File OUC bổ sung quy mô lớn và danh mục chọn.

## Mẫu bổ sung

| Workbook | Sheet | Công thức | Vùng gộp | Vai trò |
| --- | ---: | ---: | ---: | --- |
| `huangshi-tree-transplant.xlsx` | 12 | 0 | 688 | Bảng khối lượng xây dựng, nhiều ô gộp |
| `zhangye-budget.xlsx` | 15 | 0 | 58 | Bộ biểu ngân sách nhiều sheet |
| `liangzihu-budget.xlsx` | 10 | 0 | 46 | Biểu ngân sách và mục lục |
| `liangzihu-expenses.xlsx` | 1 | 0 | 1 | Header/footer tiếng Trung |

Các mẫu bổ sung thiếu công thức hoặc thiếu nhiều sheet nên không tính là mẫu
đáp ứng đồng thời các tiêu chí của người dùng. Các liên kết tải cần xác minh
thủ công/captcha không được đưa vào bộ file đã kiểm tra.

## Đối chiếu parser hiện tại

Chạy từ thư mục repository:

```bash
.venv/bin/python scripts/audit-excel-corpus.py .test-data/chinese-excel-corpus \
  --parser-max-chinese-cells 20000 --output .test-data/chinese-excel-corpus/audit.json
```

Script kiểm kê XML độc lập, tìm workbook/worksheet/shared-string qua OPC
relationships, đọc cả sheet ẩn và ô thưa, không thay đổi hay tính lại file.
Số công thức là số ô chứa phần tử `<f>`, kể cả shared-formula followers.
Rich text chỉ lấy nội dung hiển thị, không tính phonetic annotations.
Vùng gộp được đếm theo `<mergeCell>`, không phải số ô thành viên trong vùng.
Đã đối chiếu độc lập số sheet/công thức/vùng gộp của hai mẫu nhỏ chính bằng
openpyxl ở chế độ đọc; kết quả khớp.

- Trên **6 file nhỏ**, ghép source segments theo part/cell khớp đủ **2.228 ô
  chứa tiếng Trung**, không thiếu hoặc thay đổi nội dung ô thông thường.
- Tên sheet tiếng Trung chưa được đưa vào translation segments. Mẫu Hồ Nam
  và mẫu chi phí Liangzihu còn có header/footer tiếng Trung chưa được trích xuất.
- File OUC được kiểm kê đầy đủ ở mức XML, nhưng **chưa chạy converter và dịch
  toàn bộ**: vượt ngưỡng 20.000 ô tiếng Trung của lượt đối chiếu này. Giới hạn
  này thuộc script kiểm tra, không phải giới hạn hỗ trợ của converter.
- Chưa chạy dịch Argos/online, xuất workbook đã dịch, tính lại công thức hay
  kiểm tra bố cục trong Excel trên bộ dữ liệu mới. Kết quả này xác nhận cấu
  trúc file và độ bao phủ extraction trong phạm vi trên, không chứng minh
  chất lượng bản dịch hoặc độ nguyên vẹn của output.

Trong lượt này chưa sửa parser/writer. Bộ file thật này cung cấp dữ liệu để
kiểm chứng thay đổi tiếp theo; không dùng workbook tổng hợp trước đây làm
bằng chứng thay thế cho các mẫu nghiệp vụ thực tế.
