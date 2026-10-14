# Bộ PDF automotive tiếng Trung để kiểm chứng parser

Ngày lấy nguồn và kiểm tra local: 13/10/2026. Đã tải **4 PDF, 449 trang,
15.313.267 byte** từ website hãng/nhà cung cấp/cơ quan xuất bản. Mục tiêu là
đánh giá extraction trước khi đưa nội dung cho LLM dịch.

## Bộ tài liệu đã tải

| ID | PDF nguồn | Trang thực tế | Trường hợp cần kiểm tra |
| --- | --- | ---: | --- |
| bosch-kt660-zh | [Bosch KT660 用户手册](https://mediathek-bosch-automotive.com/files/bosch_wa/1697/021652.pdf) | 24 | Tài liệu thiết bị chẩn đoán: hai cột, cảnh báo, quy trình đánh số, ECU, bảng thông số và chữ trong screenshots. |
| ti-tcan1575-zh | [TI TCAN157x-Q1 CAN FD SIC transceiver, Rev. B](https://www.ti.com.cn/cn/lit/gpn/TCAN1575-Q1) | 130 | Bảng min/typ/max, ô gộp, dấu âm, đơn vị điện, timing, CAN ID, SPI và register. |
| byd-seal-zh | [BYD SEAL 中文用户手册 11/2023](https://www.bydauto.co.nz/storage/uploads/22cbd3dd-3405-4ab0-8565-428bb7199856/BYD-SEAL-OWNER%E2%80%98s-MANUAL-CH_11_2023_web.pdf) | 281 | Sách dài: chương/mục, headers, cảnh báo, bảng, hình xen với text và quy trình sử dụng/bảo dưỡng. |
| mee-vehicle-protocol-draft-zh | [重型车远程排放监控技术规范 第4部分：通讯协议及数据格式](https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202004/W020200423368281427405.pdf) | 14 | Mã hex, BYTE/WORD/DWORD, độ dài byte, giá trị báo không hợp lệ, hệ số quy đổi và bảng nối trang. Đây là bản dự thảo lịch sử dùng làm fixture, không phải hướng dẫn tuân thủ hiện hành. |

URL, SHA-256, kích thước, số trang và trang đề xuất kiểm tra nằm trong
[manifest](AUTOMOTIVE_PDF_CORPUS.json). File gốc ở
`.test-data/automotive-pdf/sources/`; không đưa bản gốc hoặc toàn bộ text trích
xuất vào Git. Tài liệu công khai không đồng nghĩa có license tái phân phối mở.

## Kiểm tra đã thực hiện

- Mở cả bốn file bằng PDFium và đếm trang từ bản tải thực tế. Số trang có trên
  50 ký tự Hán trong text layer lần lượt là **22/24, 93/130, 255/281, 14/14**.
  Đây chỉ là phép sàng lọc ngôn ngữ; không phải thước đo độ chính xác parser.
- Render và xem trực tiếp Bosch trang vật lý 3, TI trang 7, BYD trang 80 và
  MEE trang 7. Xác nhận có hai cột/bảng, bảng kỹ thuật dày đặc, hình xen text,
  và mã/số liệu tương ứng. Preview ở `.test-data/automotive-pdf/previews/`.
- Chạy **parser DocBridge hiện tại**, không gọi provider dịch, trên toàn bộ
  MEE: 14 trang, 656 segment, 20 block bảng, khoảng **1,22 giây**, peak RSS
  **417.632 KiB** trong lần chạy này. Không dùng số này để suy ra tốc độ OCR,
  sách dài hoặc so sánh với engine khác.
- Đối chiếu **5 hàng bảng trên trang 7** với bản render: mã thông tin, tốc độ
  xe, áp suất và torque. Các giá trị cần kiểm tra đều nằm đúng hàng trong output;
  có kiểm tra `WORD`/`BYTE`, `1/256`, `250.996`, `0.5` và dấu âm `-125`.
  Kết quả **5/5 spot checks đạt**, không phải chứng nhận toàn bộ tài liệu.

Raw evidence: `page-index.json`, `mee-row-checks.json`, `mee-probe.log` và
`docbridge/mee-vehicle-protocol-draft-zh/` trong `.test-data/automotive-pdf/`.
Lệnh tái chạy baseline: `.venv/bin/python .test-data/automotive-pdf/probe_docbridge.py mee-vehicle-protocol-draft-zh`.

## Những mẫu bị loại và phần chưa kiểm chứng

- **TI TCAN4550** có URL/tựa đề Trung nhưng bản tải thực tế 144 trang chỉ có
  5 trang chứa trên 50 ký tự Hán; phần lớn thân tài liệu là tiếng Anh. Đã loại
  khỏi bộ chính và thay bằng TCAN157x-Q1. Bản trên web reader còn có số trang
  khác; dùng hash của file local thay vì suy từ alias tải xuống.
- Chưa có bản scan giấy tự nhiên được xác minh. Bốn file chính đều có text
  layer; ảnh và screenshot nhúng không làm cả tài liệu trở thành PDF scan.
  Nếu raster hóa để thử OCR, phải ghi rõ đó là fixture tổng hợp.
- Sách BYD đại diện bố cục tài liệu dài, không thay thế đặc tả UDS/AUTOSAR.
  Chưa xác minh được một PDF AUTOSAR tiếng Trung phù hợp trong lượt tìm này.
- Chưa chạy bộ này qua Docling/MinerU, chưa dịch bằng external LLM và chưa đánh giá
  độ chính xác toàn bộ 449 trang. Bộ nguồn đã sẵn sàng cho phép đối chứng đó.

Khi đối chứng, giữ nguyên source/hash và so riêng: text thiếu/lặp, thứ tự đọc,
quan hệ hàng/cột, đoạn/bảng qua trang, mã/số/đơn vị, thời gian và RAM. Chỉ sau
extraction mới đưa cùng nội dung sang model dịch để tránh trộn hai loại lỗi.
