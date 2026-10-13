"""Reusable CPU inference for the pinned Argos 1.9.6 model.

Keep Argos's sentence boundaries and decoder settings, but retain the tokenizer
and model between calls. No Argos or Stanza globals are monkey-patched.
Decoder behavior adapted from Argos Translate 1.9.6, Copyright (c) 2020
Argos Open Technologies, LLC (MIT); see docs/ARGOS_RUNTIME_LICENSE.txt.
"""

from collections import OrderedDict


class ArgosRuntime:
    def __init__(self, package):
        self.package = package
        self.sentencizer = None
        self.translator = None
        self.cache = OrderedDict()

    def _prepare(self):
        if self.translator is not None:
            return
        import ctranslate2
        import stanza
        import torch

        # Tiny sentence-tokenization inputs incur overhead with many CPU threads.
        # This runs inside the dedicated translation worker.
        torch.set_num_threads(1)
        package = self.package
        self.sentencizer = stanza.Pipeline(
            lang=package.from_code, dir=str(package.package_path / "stanza"),
            processors="tokenize", use_gpu=False, logging_level="WARNING",
        )
        self.translator = ctranslate2.Translator(str(package.package_path / "model"), device="cpu")

    def translate(self, text: str) -> str:
        self._prepare()
        paragraphs = []
        for paragraph in text.split("\n"):
            if paragraph not in self.cache:
                self.cache[paragraph] = self._paragraph(paragraph)
                if len(self.cache) > 128:
                    self.cache.popitem(last=False)
            self.cache.move_to_end(paragraph)
            paragraphs.append(self.cache[paragraph])
        return "\n".join(paragraphs).lstrip("\n")

    def _paragraph(self, text: str) -> str:
        package = self.package
        sentences = [sentence.text for sentence in self.sentencizer(text).sentences]
        tokenized = [package.tokenizer.encode(sentence) for sentence in sentences]
        translated = self.translator.translate_batch(
            tokenized,
            target_prefix=[[package.target_prefix]] * len(tokenized) if package.target_prefix else None,
            replace_unknowns=True, max_batch_size=32, beam_size=4, num_hypotheses=1,
            length_penalty=0.2, return_scores=True,
        )
        # Argos decodes the concatenated sentence tokens for each paragraph.
        tokens = [token for result in translated for token in result.hypotheses[0]]
        value = package.tokenizer.decode(tokens)
        if package.target_prefix and value.startswith(package.target_prefix):
            value = value[len(package.target_prefix):]
        return value[1:] if value.startswith(" ") else value
