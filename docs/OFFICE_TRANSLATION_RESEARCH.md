# Tham khảo engine dịch Office giữ format

Ngày kiểm tra: 13/10/2026. Chỉ đọc tài liệu chính thức và source; không chạy API dịch, không benchmark các engine bên ngoài, không thay parser/runtime. Checkout được đối chiếu là DocBridge tại `7aca8ff`; bản công ty có các thay đổi trong tóm tắt của người dùng chưa nằm ở checkout này.

## Đề xuất

Ưu tiên **Okapi OpenXML Filter** làm engine đối chứng; **OmegaT** là ứng dụng CAT lâu năm để học cách giữ inline tags và kiểm tra tag trước khi xuất. Nếu cần engine có repo GitHub và giao diện convert/merge rõ ràng, thử **OpenXLIFF**. Trước mắt giữ writer OOXML của DocBridge, bổ sung kiểm chứng và đo thời gian theo giai đoạn. Chưa có bằng chứng rằng fork một app LLM mới sẽ sửa tình trạng Mac bị đơ hoặc giữ format tốt hơn.

Thiết kế phù hợp là **OOXML gốc → đoạn dịch có ID + inline codes → LLM trả text và codes → kiểm tra → merge vào package gốc**. Markdown vẫn là đầu ra riêng, không làm trung gian cho Office roundtrip. Đây là đề xuất từ đối chiếu phương pháp bên dưới, không phải tuyên bố mọi tính năng Office đã được hỗ trợ.

## So sánh ngắn

| Công cụ | Office và phương pháp đã xác minh | License chính | Cách dùng cho DocBridge |
| --- | --- | --- | --- |
| [Okapi OpenXML](https://gitlab.com/okapiframework/Okapi) | DOCX/XLSX/PPTX; XML event reader, text units, inline codes, skeleton và filter writer. | Apache-2.0 code | Engine đối chứng đầu tiên; có thể dùng CLI/JAR riêng nếu fixture chứng minh hơn parser hiện tại. |
| [OmegaT](https://github.com/omegat-org/omegat) | DOCX/XLSX/PPTX; CAT với formatting tags, kiểm tra tag và tạo file dịch. | GPL-3.0-or-later | Học segmentation/tag validation; fork cả ứng dụng kéo theo project model và Java UI khác với DocBridge. |
| [OpenXLIFF](https://github.com/maxprograms-com/OpenXLIFF) | Microsoft Office 2007+; convert ZIP/XML thành XLIFF + skeleton, merge ngược về Office. | EPL-1.0 trong source đã đọc | Ứng viên GitHub thứ hai cho prototype convert/merge; kiểm tra các part được bỏ qua. |
| [LibreOffice/UNO](https://www.libreoffice.org/) | Office object model, render và tính công thức; `XTextRange.setString()` xóa styles. | MPL-2.0, kèm dependency licenses | Giữ làm renderer/recalculation verifier; không dùng setter text đơn giản làm engine bảo toàn format. |
| [Translate Toolkit](https://github.com/translate/translate) / [Weblate](https://github.com/WeblateOrg/weblate) | Toolkit có ODF → XLIFF/PO → ODF; Microsoft Office nằm trong mục chưa hỗ trợ. Weblate quản lý localization formats. | GPL-3.0-or-later chủ đạo, các file có license khác | Hữu ích cho localization/XLIFF; không thay engine OOXML bằng bước Office → ODF → Office. |
| [argos-translate-files](https://github.com/argosopentech/argos-translate-files) | DOCX main XML và PPTX slide XML qua BeautifulSoup/Argos tags; không thấy XLSX handler. | MIT | Cùng ý tưởng sửa ZIP, nhưng coverage thấp hơn DocBridge; không chọn làm bản fork thay thế. |

Nguồn cho bảng: [Okapi filter source](https://gitlab.com/okapiframework/Okapi/-/blob/0b452b680697676abb3d8358a2941b69f0214446/okapi/filters/openxml/src/main/java/net/sf/okapi/filters/openxml/OpenXMLFilter.java), [Okapi FAQ/license](https://okapiframework.org/wiki/index.php?title=FAQ), [OmegaT README/license](https://github.com/omegat-org/omegat), [OmegaT tags](https://omegat.sourceforge.io/manual-latest/en/chapter.instant.start.guide.html), [OpenXLIFF README](https://github.com/maxprograms-com/OpenXLIFF/blob/ad44783fcb772c944ec630260a23f264123417cf/README.md), [OpenXLIFF converter/license header](https://github.com/maxprograms-com/OpenXLIFF/blob/ad44783fcb772c944ec630260a23f264123417cf/src/com/maxprograms/converters/office/Office2Xliff.java), [UNO setter](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1text_1_1XTextRange.html), [LibreOffice licenses](https://www.libreoffice.org/licenses/), [Toolkit supported formats](https://docs.translatehouse.org/projects/translate-toolkit/en/latest/formats/), [Toolkit license files](https://github.com/translate/translate/tree/0a5520d88487df194fe2813d3297a85729377817/LICENSES), [Weblate formats](https://docs.weblate.org/en/latest/formats.html), [Weblate license](https://github.com/WeblateOrg/weblate/blob/417dba0f1cf070a32a301f8cc65686ea13129537/LICENSE), [Argos DOCX](https://github.com/argosopentech/argos-translate-files/blob/7d8e48316c92d64724f9e7db8adefe6ec4ca9836/argostranslatefiles/formats/openxml/docx.py), [Argos PPTX](https://github.com/argosopentech/argos-translate-files/blob/7d8e48316c92d64724f9e7db8adefe6ec4ca9836/argostranslatefiles/formats/openxml/pptx.py), [Argos license](https://github.com/argosopentech/argos-translate-files/blob/7d8e48316c92d64724f9e7db8adefe6ec4ca9836/LICENSE).

## Okapi: tham khảo gần nhất với bài toán

**Repo chính thức hiện ở GitLab**, theo website/FAQ; không nhầm với các repo GitHub cùng tên `okapi` thuộc API gateway/web framework. Source Apache-2.0, tài liệu CC-BY-SA. [Website](https://okapiframework.org/wiki/index.php/Main_Page), [FAQ](https://okapiframework.org/wiki/index.php?title=FAQ).

`OpenXMLFilter` dùng StAX `XMLInputFactory` và API `hasNext()/next()` sinh events. `NonModifiablePart` giữ part không dịch bằng `ZipSkeleton`; `RunContainer` mô hình hyperlink/structured document tag; `BlockTextUnitWriter` ghi text và codes về XML. Đây là hướng event-based với skeleton, không phải dựng Office mới từ plain text. Source còn giữ metadata/shared strings/markup trong memory, nên **không suy ra toàn engine dùng constant memory hay chắc chắn nhanh hơn DocBridge**. [Filter](https://gitlab.com/okapiframework/Okapi/-/blob/0b452b680697676abb3d8358a2941b69f0214446/okapi/filters/openxml/src/main/java/net/sf/okapi/filters/openxml/OpenXMLFilter.java), [NonModifiablePart](https://gitlab.com/okapiframework/Okapi/-/blob/0b452b680697676abb3d8358a2941b69f0214446/okapi/filters/openxml/src/main/java/net/sf/okapi/filters/openxml/NonModifiablePart.java), [RunContainer](https://gitlab.com/okapiframework/Okapi/-/blob/0b452b680697676abb3d8358a2941b69f0214446/okapi/filters/openxml/src/main/java/net/sf/okapi/filters/openxml/RunContainer.java), [Writer](https://gitlab.com/okapiframework/Okapi/-/blob/0b452b680697676abb3d8358a2941b69f0214446/okapi/filters/openxml/src/main/java/net/sf/okapi/filters/openxml/BlockTextUnitWriter.java).

Filter có cấu hình header/footer, comments, slides/masters/notes, chart/diagram data và cached chart strings; Excel có tùy chọn extract shared string riêng theo cell. Các tùy chọn làm sạch tags/style và xóa embedded Excel package cần tắt trong phép thử giữ format. **Dịch cached chart strings chưa chứng minh workbook nhúng đã đồng bộ**, và giữ formula text chưa chứng minh SUMIF criteria còn đúng sau khi đổi nhãn. Cần render và tính lại. [Options/limitations](https://okapiframework.org/wiki/index.php/OpenXML_Filter), [Formula representation](https://gitlab.com/okapiframework/Okapi/-/blob/0b452b680697676abb3d8358a2941b69f0214446/okapi/filters/openxml/src/main/java/net/sf/okapi/filters/openxml/Formula.java).

Điểm đáng chú ý cho hiệu năng: commit `0b452b68` ngày 12/10/2026 sửa index array-formula và tránh đọc metadata worksheet ẩn không cần thiết. Có fixture khoảng 65k single-cell array formulas. Đây là bằng chứng upstream có xử lý workbook rất lớn, **không phải bằng chứng Mac đang gặp đúng lỗi này**. [Commit](https://gitlab.com/okapiframework/Okapi/-/commit/0b452b680697676abb3d8358a2941b69f0214446), [Range index test](https://gitlab.com/okapiframework/Okapi/-/blob/0b452b680697676abb3d8358a2941b69f0214446/okapi/filters/openxml/src/test/java/net/sf/okapi/filters/openxml/ArrayFormulaRangesTest.java).

Nguồn được đọc gồm raw source tại SHA trên và Maven sources JAR `okapi-filter-openxml:1.48.0` (~396 kB); không tải/cloning toàn framework. [Release sources](https://repo.maven.apache.org/maven2/net/sf/okapi/filters/okapi-filter-openxml/1.48.0/okapi-filter-openxml-1.48.0-sources.jar).

## OmegaT / OpenXLIFF: pattern có thể học

OmegaT coi bold/italic và cấu trúc inline là tags trong câu. Tag sai có thể làm file output không mở được; CLI có `--tag-validation=abort`. Filter OOXML đời cũ được đánh dấu legacy, không nên lấy cấu hình legacy làm mặc định mới. [Tag handling](https://omegat.sourceforge.io/manual-latest/en/chapter.instant.start.guide.html), [CLI](https://omegat.sourceforge.io/manual-latest/en/chapter.how.to.html), [Filter options](https://omegat.sourceforge.io/manual-standard/en/chapter.appendices.html), [Current OOXML filter API](https://omegat.sourceforge.io/javadoc-standard/org/omegat/filters4/xml/openxml/OpenXmlFilter.html).

OpenXLIFF có đường đi ngược thật: `Office2Xliff` tạo ZIP skeleton và XLIFF per XML part; `MSOffice2Xliff` biến run markup thành placeholder `<ph>`; `Xliff2Office` merge XML skeleton vào ZIP. Source bỏ qua `slideMaster`, `slideLayout`, `handoutMaster`, `notesMaster` trong vòng XML extraction; nested workbook ZIP không được parse đệ quy trong đường đi đã đọc. Nó không là drop-in bảo đảm đủ chart/SmartArt/formula dependency cho DocBridge. [Extraction](https://github.com/maxprograms-com/OpenXLIFF/blob/ad44783fcb772c944ec630260a23f264123417cf/src/com/maxprograms/converters/office/Office2Xliff.java), [Inline conversion](https://github.com/maxprograms-com/OpenXLIFF/blob/ad44783fcb772c944ec630260a23f264123417cf/src/com/maxprograms/converters/msoffice/MSOffice2Xliff.java), [Merge](https://github.com/maxprograms-com/OpenXLIFF/blob/ad44783fcb772c944ec630260a23f264123417cf/src/com/maxprograms/converters/office/Xliff2Office.java).

## Repo LLM: README giữ format chưa đủ

Các project sau là **tham khảo kỹ thuật nhỏ**, không gọi là công cụ nổi tiếng: tại thời điểm đọc GitHub API, CrispTranslator có 1 star, `pptx-translate` 0, `doc-translator` 2, Lebab 0. Không dùng số stars làm bằng chứng chất lượng; dùng source để kiểm tra phương pháp.

- **[CrispTranslator](https://github.com/CrispStrobe/CrispTranslator)** (AGPL-3.0): DOCX, dịch đoạn rồi word alignment để chuyển bold/italic. `apply_aligned_formatting` xóa runs và tạo lại theo target whitespace tokens; footnote references của body được chuyển về cuối paragraph; paragraph chứa drawing/field có thể bị bỏ qua. Học được ý tưởng semantic alignment, nhưng không chọn làm writer mặc định; alignment thêm chi phí CPU/model và cấu trúc được dựng lại. [Pinned implementation](https://github.com/CrispStrobe/CrispTranslator/blob/21dfd575d87f888f18ce0dade9ea1fb7767f7276/translator.py), [License](https://github.com/CrispStrobe/CrispTranslator/blob/21dfd575d87f888f18ce0dade9ea1fb7767f7276/LICENSE).
- **[pptx-translate](https://github.com/Vncntvx/pptx-translate)** (MIT): sửa OOXML trực tiếp, gửi `[[R0]]...[[/R0]]` từng run trong cùng translation unit và kiểm tra marker. Khi marker mất, writer chia target theo tỷ lệ độ dài source runs. Pattern marker/guard hữu ích; fallback tỷ lệ ký tự không chứng minh bold/hyperlink nằm đúng từ sau đổi word order. Có chart-deep/SmartArt code nhưng chưa chứng minh cache + embedded workbook nhất quán qua render/tính lại. [Markers](https://github.com/Vncntvx/pptx-translate/blob/859927dd36a0e5981210149f5a65414606dfc790/src/translation/marker.ts), [Writer](https://github.com/Vncntvx/pptx-translate/blob/859927dd36a0e5981210149f5a65414606dfc790/src/pptx/writer.ts), [Fallback](https://github.com/Vncntvx/pptx-translate/blob/859927dd36a0e5981210149f5a65414606dfc790/src/run-preservation/distribute.ts), [Chart](https://github.com/Vncntvx/pptx-translate/blob/859927dd36a0e5981210149f5a65414606dfc790/src/pptx/chart-deep.ts), [License](https://github.com/Vncntvx/pptx-translate/blob/859927dd36a0e5981210149f5a65414606dfc790/LICENSE).
- **[doc-translator](https://github.com/ilysom0611/doc-translator)** (MIT): DOCX/PPTX write-back đưa toàn target paragraph vào một carrier run rồi làm rỗng các run khác. PPTX loại chart/SmartArt với warning; XLSX handler dùng openpyxl và code tuyên bố chấp nhận không giữ embedded objects. Như vậy không có lợi hơn writer DocBridge về mixed formatting/coverage. Đây là quan sát source, không mở rộng warning này thành tuyên bố rằng openpyxl luôn làm mất mọi chart. [DOCX writer](https://github.com/ilysom0611/doc-translator/blob/905090b99575cd2d45643554671349613451b2d7/app/formats/docx_fmt.py), [PPTX](https://github.com/ilysom0611/doc-translator/blob/905090b99575cd2d45643554671349613451b2d7/app/formats/pptx_fmt.py), [XLSX](https://github.com/ilysom0611/doc-translator/blob/905090b99575cd2d45643554671349613451b2d7/app/formats/xlsx_fmt.py), [License](https://github.com/ilysom0611/doc-translator/blob/905090b99575cd2d45643554671349613451b2d7/LICENSE).
- **[Lebab](https://github.com/soyrochus/lebab)** (MIT): DOCX/PPTX, gán `para.text` hoặc `shape.text`; không có XLSX adapter. Setter thay toàn nội dung mất mixed run formatting; `await` từng chunk cũng chưa có nghĩa chạy song song. [Source](https://github.com/soyrochus/lebab/blob/d802378b41643f205895643d1b0c1c5b11bebf52/lebab.py), [License](https://github.com/soyrochus/lebab/blob/d802378b41643f205895643d1b0c1c5b11bebf52/LICENSE.txt), [python-docx setter](https://python-docx.readthedocs.io/en/latest/api/text.html#docx.text.paragraph.Paragraph.text).

**[gpt_academic](https://github.com/binary-husky/gpt_academic)** là dự án LLM nổi tiếng (~71k stars khi đọc API), nhưng Word plugin đã kiểm tra là `Word_Summary`: đọc `doc.paragraphs` thành plain text, gọi LLM tóm tắt rồi ghi history. Không có Office write-back trong plugin này. Vì vậy mức độ nổi tiếng không khiến nó thành engine DOCX roundtrip. Không suy ra mọi plugin của toàn repo đều thiếu chức năng tương tự. [Pinned Word plugin](https://github.com/binary-husky/gpt_academic/blob/d6bde0fa54373309bd05823a49bda8da019d2c77/crazy_functions/Word_Summary.py), [GPL license](https://github.com/binary-husky/gpt_academic/blob/d6bde0fa54373309bd05823a49bda8da019d2c77/LICENSE).

## Cách áp dụng có thể kiểm chứng

1. Tách phép đo `parse`, `pack`, `HTTP`, `checkpoint`, `write`, và độ trễ event loop UI. Cảm giác app bị đơ không tự chứng minh parser chậm; cần profile đúng file và đúng bản Mac/company.
2. Giữ package gốc và anchor. Với mixed formatting, cho LLM dịch cả câu chứa inline codes thay vì từng run cô lập; kiểm tra ID, tags mở/đóng, số lần xuất hiện, protected numbers và hyperlink/field boundaries trước merge. Nếu validation lỗi, retry nhỏ hơn hoặc giữ nguyên unit kèm warning, không lặng lẽ gom vào run đầu.
3. Prototype Okapi/OpenXLIFF bằng subprocess riêng, chưa nhúng/fork cả UI. Dùng identity/pseudo-translation trước để chứng minh roundtrip độc lập khỏi LLM latency/quality.
4. Fixture bắt buộc: DOCX bold/italic/hyperlink/tab/break/header/footnote/textbox; PPTX grouped shapes/table/notes/chart/SmartArt; XLSX rich/shared strings, chart workbook và criteria formula. So output part names, relationships/media, XML text coverage; render trong Office/LibreOffice; tính lại formula.
5. Chỉ thay reader/writer khi benchmark cùng fixture chứng minh lợi ích. Giữ các xử lý đang có của DocBridge như cloned shared strings theo cell, chart/workbook binding, criteria SUMIF/COUNTIF nếu engine đối chứng không đáp ứng. Hiện chưa có kết quả đối chứng runtime để chốt việc đổi engine.

Các bước này là đề xuất implementation/validation; nghiên cứu chưa import code từ repo nào và chưa tạo fork.

## Lỗi UI tái hiện được trong checkout hiện tại

Đã đo trực tiếp `MainWindow.poll()` với Qt thật, 30 job trong SQLite thật và
500 event tiến độ trong queue. Fixture không parse Office và không gọi API:

| Phép đo | Trước sửa | Sau sửa source local |
| --- | ---: | ---: |
| Thời gian một lượt `poll()` trên GUI thread | 1,732 giây | 0,00424 giây |
| Số lần dựng lại toàn bộ bảng trong lượt đó | 500 | 1 |
| Event còn lại cho các lượt tiếp theo | 0 | 436 |

Các số này mô tả một burst tổng hợp, không phải tốc độ dịch file thực tế hoặc
phép đo trên Mac. Nhưng chúng chứng minh có thể làm giao diện đứng dù không
chạy parser: code cũ drain queue không giới hạn và dựng lại bảng theo từng event.

Source local đã giới hạn mỗi tick tối đa 64 event / khoảng 8 ms cho việc đọc
queue, gộp cập nhật bảng và trả quyền điều khiển về Qt. Chi phí vẽ bảng/đọc SQLite
nằm ngoài ngân sách đọc queue; đây không phải cam kết mọi tick dưới 8 ms. Khi
worker đã thoát, UI xử lý backlog trước khi hoàn tất để tiến độ cũ không ghi đè
trạng thái Done. Parser, providers và nội dung export không thay đổi.

Hai regression test UI đã fail trước sửa và pass sau sửa: progress burst vẫn nhường
event loop, giữ selection/tiến độ cuối; worker thoát vẫn xử lý backlog rồi mới
reset trạng thái. Toàn bộ suite: 131 pass, 1 skip. Raw reports và harness ở
`.test-data/office-ux-investigation/`; patch riêng là `ui-progress-fix.patch`
trong thư mục đó. Chưa áp dụng patch vào repo công ty, chưa build hay kiểm chứng
trên Mac. Cần checkout/commit và file gây lỗi để xác nhận nguyên nhân của bản đó.

Ngoài ra, pipeline trước đây chỉ gửi event “Đang dịch” sau khi nhận được phần
dịch hoàn thành đầu tiên. Vì UI ưu tiên thông báo progress gần nhất hơn status
trong SQLite, nhãn “Đang phân tích tài liệu” có thể tồn tại suốt thời gian pack
batch/chờ LLM dù parser đã xong. Regression test đã tái hiện nhãn sai ngay tại
thời điểm gọi provider đầu tiên. Source local nay gửi event bắt đầu dịch với số
đoạn đã hoàn thành trước khi pack/gọi provider; đây là cập nhật trạng thái,
không tăng tốc hay sửa nội dung parser. Test này pass sau sửa.
