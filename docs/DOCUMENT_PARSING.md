# Document parsing và Unlimited-OCR

Đánh giá ngày 12/10/2026; chỉ đọc tài liệu và mã chính thức, chưa tải weights hay chạy inference. **Khuyến nghị:** giữ parser Office hiện tại; thử Unlimited-OCR như một backend tùy chọn cho PDF scan/bố cục khó, chạy ở dịch vụ riêng. Bỏ màn hình Review là lựa chọn UX độc lập; parsing tốt hơn không tự sửa lỗi ngữ nghĩa của Argos hoặc LLM dịch.

## Converter đã có parsing

- `src/converter/office.py` đọc OOXML, tạo segments có anchor tới phần tử gốc, rồi patch nội dung vào Office khi xuất. Chuyển Office thành ảnh rồi OCR sẽ phải dựng lại cấu trúc và mất đường dẫn patch trực tiếp; đây là suy luận từ kiến trúc hiện tại.
- `src/converter/pdf.py` đọc text/bảng bằng pdfplumber, render trang bằng PDFium và dùng Tesseract khi cần OCR. PDF xuất thành DOCX dựng lại hoặc Markdown; không bảo đảm giữ nguyên font/bố cục.
- `src/converter/pipeline.py` đã tách parse → translate → export; `models.py` có `Document`, `Block`, `Segment`, bbox/page/source anchor. Đây là seam phù hợp để thêm parser mà giữ provider dịch độc lập.

## Các thông tin đã xác minh

| Nội dung | Nguồn và giới hạn |
| --- | --- |
| Model | Model card ghi khoảng **3B**, BF16, MIT. [Model card Baidu](https://huggingface.co/baidu/Unlimited-OCR). Paper ghi MoE **3B tổng / 0.5B activated**, không phải model dense. [Paper, bảng 1](https://arxiv.org/html/2606.23050v1). |
| Download | File weights `model-00001-of-000001.safetensors` được liệt kê **6.67 GB**; toàn repo **6.78 GB**. [Danh sách file](https://huggingface.co/baidu/Unlimited-OCR/tree/main). Index ghi tổng tensor bytes `6,672,212,480` (không phải toàn bộ dung lượng cài đặt). [Weight index](https://huggingface.co/baidu/Unlimited-OCR/blob/main/model.safetensors.index.json). Vì vậy bản BF16 không phù hợp mục tiêu bundle dưới 2 GB trong `docs/DESIGN.md`. |
| Runtime | Hướng dẫn Transformers dùng NVIDIA GPU, Python 3.12.3 + CUDA 12.9, Torch 2.10.0 / Transformers 4.57.1, BF16 và `.cuda()`. Không có quy trình CPU-only được kiểm chứng trong hướng dẫn này. [README](https://github.com/baidu/Unlimited-OCR#transformers). |
| GPU | Recipe vLLM nói một GPU **>=8 GB VRAM** đủ BF16. Đây là tuyên bố của recipe, chưa được kiểm chứng trên máy này hoặc cho mọi số trang/concurrency. Recipe yêu cầu image phát hành riêng; ghi architecture chưa ở stable pip wheel tại thời điểm kiểm tra. [vLLM recipe](https://recipes.vllm.ai/baidu/Unlimited-OCR). |
| Context | Config ghi `max_position_embeddings=32768`. [Config](https://huggingface.co/baidu/Unlimited-OCR/blob/main/config.json). Transformers truyền `max_length=32768` vào generate; không đồng nghĩa luôn có 32K token đầu ra ngoài input. [Mã inference](https://huggingface.co/baidu/Unlimited-OCR/blob/main/modeling_unlimitedocr.py). |
| Số trang | Paper có tập multi-page huấn luyện 2–50 trang và đánh giá tới 40+; không công bố một hard limit trang áp dụng cho mọi tài liệu. Paper thừa nhận finite context/prefill vẫn giới hạn, dù tên là Unlimited. [Paper, §4–6](https://arxiv.org/html/2606.23050v1). |
| Đầu vào | PDF được render thành ảnh rồi infer multi-page; single-page có gundam/base, multi-page hướng dẫn dùng base 1024, không crop. [README](https://github.com/baidu/Unlimited-OCR#transformers). |
| Đầu ra | Mã nhận cả marker category+bbox dạng `<\|det\|>label [box]<\|/det\|>` và cặp ref/det; phân loại riêng `image`, lưu crop ảnh, `result.md`, ảnh có bbox; multi-page tách bằng `<PAGE>`. Đây không phải API trả `Document` JSON có schema cố định. [Mã postprocess](https://huggingface.co/baidu/Unlimited-OCR/blob/main/modeling_unlimitedocr.py). Paper mô tả tọa độ training chuẩn hóa 0–1000 và đánh giá text, formula, bảng, thứ tự đọc; cần xác minh output thực trước khi đổi bbox sang hệ tọa độ PDF. [Paper](https://arxiv.org/html/2606.23050v1). |

## API không chỉ là thay URL/model dịch

vLLM cung cấp OpenAI-compatible chat nhưng cần content ảnh `image_url`, prompt bắt đầu `<image>`, `skip_special_tokens=false`, server đăng ký n-gram logits processor và request có `vllm_xargs` (`ngram_size=35`, `window_size=128`, multi-page 1024). Recipe cảnh báo thiếu recipe có thể trả rỗng. [Recipe vLLM](https://recipes.vllm.ai/baidu/Unlimited-OCR).

SGLang trong README dùng wheel riêng, prompt client khác, `images_config`, `custom_logit_processor`, `custom_params`, streaming. Vì vậy adapter vLLM và SGLang cần payload riêng; `OnlineProvider` hiện chỉ gửi text/model/temperature/max_tokens để dịch. [README SGLang](https://github.com/baidu/Unlimited-OCR#sglang). Chưa kiểm chứng tương thích của endpoint bên thứ ba.

## Đề xuất tích hợp, chưa triển khai

1. Đặt `DocumentParser` trước translation, trả `Document` với blocks, segments, assets, nguồn parser/model/version và warnings. Office luôn giữ anchor OOXML; PDF dùng native parser mặc định, cho chọn vision service theo job.
2. Settings có mục **Document parsing** riêng: backend Native / Unlimited-OCR vLLM / SGLang, API URL, model, auth, timeout, pages/request, max output/context và test connection. Cấu hình và API key tách khỏi dịch.
3. Render theo trang, giữ page index/kích thước; normalize category, bbox, bảng, Markdown/HTML qua adapter. Không đưa raw markup vào toàn bộ một translation request; dịch theo block/cell, giữ code/số/URL/glossary.
4. Giới hạn số trang/token/response bytes; phát hiện output bị cắt hoặc thiếu `<PAGE>`, chia nhỏ batch, checkpoint từng trang. Cache theo source hash + parser settings/model; parser đổi phải parse lại.
5. Dịch vụ tách khỏi bundle desktop, có thể localhost hoặc máy GPU trong mạng. Chỉ chạy khi người dùng chọn backend đó; lỗi dịch vụ báo rõ, fallback native theo cấu hình.

Trước khi chọn làm mặc định, cần smoke test cùng PDF Bosch/AUTOSAR thật: text/bảng/reading order, thiếu/lặp trang, bảo toàn identifier và chất lượng DOCX/Markdown sau dịch. Tốc độ, VRAM thực, ngôn ngữ tiếng Việt, chất lượng scan/bảng kỹ thuật và fidelity xuất Office hiện **chưa được test**. Không suy ra chất lượng dịch hoặc mức cải thiện trên tài liệu người dùng từ benchmark paper.
