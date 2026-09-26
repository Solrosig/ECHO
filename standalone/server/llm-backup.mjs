// Qwen is a locked backup language model (decision 2026-09-11). Nothing selects it until a dedicated commit sets
// QWEN_BACKUP_ALLOWED to true. Even then only the server selects it, with ECHO_LLM_BACKUP=1, and it runs on the same
// local Ollama as the primary model. The frontend never names it.
export const QWEN_BACKUP_ALLOWED=false;
export const QWEN_BACKUP_MODEL='qwen2.5:1.5b';

// WebLLM bundle revision shipped with ECHO standalone 1.5.0. The bundle lives in the release asset, not in git; the
// static-file host still resolves its URL layout.
export const QWEN_REVISION='a822ee410075710c9673005eafa017b90136b85d';
