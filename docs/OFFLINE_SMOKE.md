# Local Argos verification

Tested on 2026-10-12 with Argos Translate 1.9.6, torch 2.5.1+cpu,
CTranslate2 4.8.2 and the Chinese → English 1.9 package.

Model downloaded through the [official Argos package index](https://www.argosopentech.com/argospm/index/):
[translate-zh_en-1_9.argosmodel](https://argos-net.com/v1/translate-zh_en-1_9.argosmodel).
Size: 74,481,402 bytes. Observed SHA-256:
`62e7af5a3a48b530e47b7b3e5c78c2de79073ecd815750d2bf3ab35b4a67da2d`.
The archive CRC and language metadata were verified. This hash records the download;
it is not a separately published upstream checksum.

The test blocked Python socket connections while loading the local package and
translating. No API key or online translation service was used. DOCX, PPTX, XLSX,
text PDF and Chinese scanned PDF all produced Office and Markdown outputs.
The latest scan test recognized the exact ABS source phrase using a Simplified
Chinese CJK font. Earlier font output produced an OCR substitution, which shows
why the OCR/source review step matters.

Raw results and files are local ignored artifacts under
`.test-data/argos-local-verified/report.json` and `outputs/`.
The smoke runner is `.test-data/argos-local/smoke.py`.

## Translation samples

Source: 你好，这是一个离线翻译测试。

Without glossary: Hello, this is an offline translation test.

With glossary: Hello, this is an offline translation test.

Source: 防抱死制动系统可以防止车轮抱死。

Without glossary: The death-proof brake system prevents the wheel from dying.

With glossary: Antilock Braking System (ABS) It can prevent the wheel from dying.

Source: 运行时环境连接应用软件组件和基础软件。

Without glossary: Operating-time environment interface application software components and basic software.

With glossary: Runtime Environment (RTE) Connection Application Software Component (SWC) and Basic Software (BSW)。

Source: 传感器 AC-123 的工作电压为12 V，压力为100 kPa。

Without glossary: Sensors AC-123 _Other Organiser 12 V, pressure is 100 kPa。

With glossary: Sensors AC-123 _Other Organiser 12 V, pressure is 100 kPa。

## Documents

- automotive.docx: Office + Markdown exported; 8 translated segments.
- automotive.pptx: Office + Markdown exported; 1 translated segments.
- automotive.xlsx: Office + Markdown exported; 2 translated segments.
- automotive.pdf: Office + Markdown exported; 2 translated segments.
- automotive-scan.pdf: Office + Markdown exported; 3 translated segments.

Word bold formatting and spreadsheet formula preservation verified.

Translation quality requires review: the brake/wheel sentence and voltage sentence contain semantic errors.
See report.json for the OCR source text and whether the exact ABS term was recognized.