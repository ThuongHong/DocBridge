# Translation performance diagnosis

Measured on 2026-10-13 against commit `18ab932`, on Linux with an Intel
i5-13500H, Argos Translate 1.9.6, and the existing Chinese-English model.
The diagnosis below describes that baseline; the implementation results at the
end describe the subsequent optimization. No paid API calls or Qwen inference
were performed.

## Where the time goes

| Fixture | Extract / OCR | Prepare Argos | Translate | Export Office |
| --- | ---: | ---: | ---: | ---: |
| Chinese DOCX, 13 segments | 0.105 s | 1.458 s | 3.716 s | 0.041 s |
| Chinese scanned PDF, 2 pages, 12 segments | 10.556 s | Already prepared | 2.450 s | 0.104 s |

The PDF ran after the DOCX in the same process, so its translation timing is
warm and can benefit from Argos's cache of previously translated text. These
small fixtures are examples, not throughput guarantees for arbitrary documents.

Office extraction does not use OCR. The scan is dominated by extraction and OCR:
13 Tesseract invocations took 7.623 seconds, with the remaining extraction time
spent on rendering, layout processing and other work. OCR is called for whole
pages, individual table cells, and retries of weak lines. The default language
selection loads Simplified Chinese, Traditional Chinese and English. Retries
were introduced to preserve source text quality; removing them needs separate
OCR accuracy validation.

## Offline findings

- `ArgosProvider.prepare()` explicitly sets `ARGOS_DEVICE_TYPE=cpu`. This build
  uses CPU PyTorch; the inspected machine has Intel Iris Xe graphics and no
  NVIDIA GPU. GPU inference is not enabled by the current application.
- The installed Argos 1.9.6 implementation constructs `stanza.Pipeline` inside
  `apply_packaged_translation` for each uncached paragraph. A minimal probe of
  three distinct short segments created three tokenizer pipelines. A second
  probe of 12 distinct segments created 12.
- The application calls Argos sequentially for individual segments/chunks.
  `batch_chars=1500` is a pipeline checkpoint boundary, not a single neural
  inference batch. Protection failures can add acronym and fragment retries;
  the scan probe made 12 Argos calls for 10 Chinese-containing segments.
- Each new UI translation run starts a new worker process, losing the loaded
  runtime/model and in-memory translation cache. Preparation and first-use costs
  vary with OS caches: the initial instrumented probe took 3.183 seconds to
  prepare and 2.743 seconds for its first short translation; subsequent fresh
  comparison processes took roughly 1.4–1.6 seconds to prepare and 1.0–1.2
  seconds for their first translation.

Controlled experiments, after a separate warm-up, on the same 12 distinct
short Chinese segments:

| Experiment | Translation time | Tokenizer constructions during measured work |
| --- | ---: | ---: |
| Current runtime, 12 PyTorch threads | 2.809 s | 12 |
| Reuse tokenizer, 12 threads | 2.358 s | 0 |
| Reuse tokenizer, 1 thread | 1.314 s | 0 |

The final experiment was **2.14 times faster** than the baseline on this fixture.
All 12 output strings matched exactly across the three experiments. Reducing
threads substantially reduced Stanza inference overhead for these tiny inputs;
it does not establish that one thread is optimal for every machine or workload.
Only the diagnostic process was modified; no global patch was shipped.

## Online findings

The actual provider and pipeline were exercised with an in-process HTTP mock,
120 Chinese segments, 3,000 source characters, and a fixed 10 ms mock response
delay. Responses echoed protected input to exercise request splitting and
decoding; this tests scheduling, not translation quality or vendor latency.

| Configuration | Pipeline batches | HTTP requests | Context characters sent |
| --- | ---: | ---: | ---: |
| Current defaults | 1 | 16 | 3,000 |
| Remove context equal to the source | 1 | 8 | 0 |
| 32,768-token input configuration, original context | 1 | 1 | 3,000 |

The default context window is 8,192 tokens, with 4,096 reserved for output and
512 for safety, leaving a 3,584-token estimated input budget. The estimator
conservatively counts UTF-8 bytes, including JSON and chat overhead; a Chinese
character commonly occupies three UTF-8 bytes. Thus `batch_chars=6000` does not
mean a 6,000-character request will fit. Recursive splitting produces many
smaller requests, all executed sequentially.

PDF segments commonly have `context == source`; Office segments may repeat the
same paragraph context across multiple styled segments. Duplicate context adds
input and reduces batch size. Increasing the configured window is valid only
when the selected endpoint/model actually supports it; the 32,768-token case is
a scheduling experiment, not a recommendation to invent a model limit.

The pipeline updates progress only after its outer batch completes, so all 16
subrequests in this example occur before the first translation progress update.
This can make a working application look stalled. Transport failures, HTTP
429/5xx retries and timeouts can add delays, but no live endpoint trace was
available to establish whether those contribute to the user's online runs.

Saving the document checkpoint took 0.003 seconds in the baseline mock run;
it was not the bottleneck for this fixture. Very large documents need their own
measurement before changing checkpoint durability.

## Recommended order

1. Reuse the offline sentence tokenizer and benchmark a small CPU thread count,
   retaining identical translation/protection behavior.
2. Omit online context when it is identical to source; pack requests against the
   existing context budget and expose progress for each actual request.
3. Measure PDF OCR separately in the UI, then optimize repeated OCR invocations
   while retaining the existing source-quality checks.
4. Consider true inference batching, persistent workers or bounded online
   concurrency only after these smaller changes are validated. Keep context
   guards and rate-limit handling intact.

## Reproduction and sources

Local diagnostic prototypes and raw measurements are under the ignored
`.test-data/performance/` directory:

- `offline_probe.py`: minimal repeated-initialization probe; its assertion failed
  at baseline and passes after the optimization.
- `offline_compare.py baseline`, `cache`, `cache-threads`: controlled runtime
  experiments and output-equality evidence.
- `online_probe.py`: mock scheduling comparisons; its final assertion now checks
  the optimized request limit.
- `phases.py`: actual Office/PDF parsing, local Argos translation, OCR-call and
  Office-export timings.

Run these scripts using `.venv/bin/python` from the repository root. Their
changes are confined to the diagnostic process and test-data directory.

Primary references:

- [Argos 1.9.6 implementation](https://github.com/argosopentech/argos-translate/blob/v1.9.6/argostranslate/translate.py)
  (the installed source was used for the version-specific diagnosis).
- [CTranslate2 performance recommendations](https://opennmt.net/CTranslate2/performance.html):
  true inference batches and thread configuration matter for throughput.
- [CTranslate2 threading and parallelism](https://opennmt.net/CTranslate2/parallel.html):
  multiple workers require concurrently submitted work to provide parallelism.

## Implemented optimization

The application now uses a reusable `ArgosRuntime` for the pinned model. It
retains one Stanza tokenizer and one CPU CTranslate2 translator, uses one
PyTorch tokenizer thread and keeps a bounded cache of 128 translated paragraphs.
Sentence boundaries, beam size 4, one hypothesis, length penalty 0.2, target
prefix handling and glossary/protected-value checks retain their previous
behavior. The adapter does not monkey-patch third-party modules.

On 27 distinct Chinese segments from the existing Office/PDF validation corpus,
including multiline text, the previous runtime took **7.369 seconds** and the
new runtime took **3.214 seconds**: **2.29 times faster**, with all output strings
identical. Both runtimes were measured in one fresh diagnostic process; OS
model/file caches and first-use setup can affect these timings.

Online requests now omit context when it equals the unmasked source and greedily pack items
against the unchanged conservative token budget. Item-size accounting is linear
and includes JSON escaping. The same 120-segment mock fixture now takes
**6 requests instead of 16**, without increasing the configured context window
or output limit. When protection masks terms or values, original source context
is retained so the model can still understand the placeholders. The source
order and protected values are retained. No live provider latency or throughput
was measured.

Completed online request results are checkpointed and reported incrementally.
Pause/resume tests verify that already saved results survive interruption and
are not sent again. Server context errors and truncated replies still trigger
safe splitting, and authentication, retry and cancellation tests pass. Long
single-segment splits are committed only when that complete segment is ready.
The online prompt instructions and fingerprint remain unchanged, preserving
resume compatibility for existing jobs parsed with the current adapter.

OCR was also measured with `OMP_THREAD_LIMIT=1`: repeated default extraction
took 8.283 seconds versus 7.674 seconds with one thread, with identical source
text and geometry. This modest fixture-specific gain is exploratory; the OCR
defaults and source-quality retries remain unchanged.

The rebuilt Linux worker completed DOCX, PPTX, XLSX and scanned-PDF translation
and original-language Markdown conversion with network connections disabled.
Translations and every uncompressed Office ZIP member matched the previous
validated release exactly, including the reconstructed PDF's DOCX. This ties
the new runtime to the previously rendered and inspected outputs.

Validation: 128 tests pass, one unrelated missing-font OCR fixture is skipped;
Ruff and whitespace checks pass. Frozen runtime startup, local inference and
all four input formats were verified. New raw reports include
`optimized-report.json`, `online-optimized-report.json`, `ocr-thread-report.json`,
`frozen-smoke.json`, and `frozen-parity.json` under `.test-data/performance/`.
The frozen online worker also passed against a local mock HTTP server, issuing
six requests and reporting completed counts 22, 44, 66, 88, 110 and 120 before
export; this is recorded in `frozen-online/report.json`.
