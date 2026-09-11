# ECHO speech service: provenance and modifications

This academic service uses original upstream TTS implementations and pinned public model files. It does not imitate another engine with substitute audio. All outputs are synthetic speech. Model revisions are recorded in `models.lock.json`.

- Chatterbox 0.1.2, Resemble AI, MIT: vendored from its PyPI wheel. The distribution-version lookup is replaced with the literal release number because the code is vendored. The upstream Perth watermark remains enabled.
- StyleTTS2 community package 0.1.6, MIT, implementing Li et al. StyleTTS2: checkpoint and support-file URLs are pinned at runtime. Alpha 0.3, beta 0.7 and five diffusion steps are explicit. Style is a diffusion/reference mixture, not solely reference transfer.
- CosyVoice source commit 8555549e882236e6541748b1042d95693caa82ba, Apache 2.0; its pinned Matcha-TTS submodule is MIT. The vendored frontend skips optional WeText normalizer construction when ECHO_TEXT_FRONTEND=0. Rendering explicitly disables that normalizer and passes the English text unchanged to the tokenizer. This avoids an unused ModelScope dependency download. CUDA stream creation is deferred to the GPU function on ZeroGPU; model weights are still placed on CUDA at startup. The same neutral speaker reference is used for every emotion; instructions control delivery.
- ZipVoice source commit 2f7326fbfe999a3ad179e3f1af82a424d4a62819, Apache 2.0: reference audio and its matching transcript condition generation. No discrete native emotion-label API is claimed.
- Parler-TTS source commit d108732cd57788ec86bc857d99a6cabd66663d68, Apache 2.0: an emotion instruction, fixed Jon speaker cue and recording-quality clause condition generation.

The original loaders require checkpoint metadata beyond tensors. The entry point sets weights_only=False for their pinned research checkpoints under PyTorch 2.8. No user-supplied weights, file paths or model URLs are accepted. Python dependencies are fixed in requirements.txt; upstream license texts accompany vendored sources.

## Reference recordings

Livingstone, S. R., & Russo, F. A. (2018), RAVDESS. Paper: https://doi.org/10.1371/journal.pone.0196391 ; dataset: https://doi.org/10.5281/zenodo.1188976 . CC BY-NC-SA 4.0: https://creativecommons.org/licenses/by-nc-sa/4.0/ . Retain attribution and this license for derived reference recordings. No endorsement is implied.

Five actor-03 speech recordings (normal intensity, statement 01, repetition 01) are converted to mono and peak-normalised to 0.8. No pitch or duration transformation is applied to the references. Original filenames, hashes and derived hashes are in refs/provenance.json. These bundled references are for noncommercial academic use. Do not describe the complete bundle as unrestricted commercial software merely because several model licenses are permissive.

The service temporarily caches generated WAV files, scheduled for deletion in five-minute intervals once they are at least five minutes old. It receives only text, engine, chosen emotion and condition. Nicknames and listener ratings remain in the separate ECHO database.
