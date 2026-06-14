import api from "@/lib/api";

/**
 * Upload a single file using the resumable chunked-upload protocol.
 *
 * Phases:
 *   1. POST /videos/upload/init       → { upload_id, chunk_size_mb }
 *   2. For each chunk in order:
 *        POST /videos/upload/<id>/chunk
 *        with the raw chunk bytes as the body.
 *   3. POST /videos/upload/<id>/finish → returns the new Video doc.
 *
 * Retries each chunk up to `retriesPerChunk` times with exponential backoff.
 * On any unrecoverable error, the partial upload is aborted server-side.
 *
 * @param {Object}   args
 * @param {File}     args.file           — the File / Blob to upload
 * @param {Object}   args.metadata       — { title, description, tags, category_id, access_tier, is_short }
 * @param {Function} [args.onProgress]   — (loaded:number, total:number) → void
 * @param {AbortSignal} [args.signal]    — optional cancellation signal
 * @param {number}   [args.retriesPerChunk=3]
 * @returns {Promise<Object>} the created Video document
 */
export async function uploadVideoChunked({
  file,
  metadata,
  onProgress,
  signal,
  retriesPerChunk = 3,
}) {
  if (!file) throw new Error("file is required");

  // ── 1) init ────────────────────────────────────────────────────────────────
  const initRes = await api.post("/videos/upload/init", {
    filename: file.name,
    total_size: file.size,
    mime_type: file.type || "application/octet-stream",
  });
  const uploadId = initRes.data.upload_id;
  const chunkSize = Math.max(1, parseInt(initRes.data.chunk_size_mb || 25, 10)) * 1024 * 1024;
  const totalChunks = Math.max(1, Math.ceil(file.size / chunkSize));

  // ── 2) upload chunks sequentially ─────────────────────────────────────────
  let offset = 0;
  for (let i = 0; i < totalChunks; i++) {
    if (signal?.aborted) {
      await api.delete(`/videos/upload/${uploadId}`).catch(() => {});
      throw new Error("Upload cancelled");
    }
    const end = Math.min(offset + chunkSize, file.size);
    const blob = file.slice(offset, end);

    let attempt = 0;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      try {
        await api.post(`/videos/upload/${uploadId}/chunk`, blob, {
          headers: { "Content-Type": "application/octet-stream" },
          // Provide both onUploadProgress (cumulative for the chunk) and
          // the running offset so the caller sees a smooth global %.
          onUploadProgress: (e) => {
            const loaded = offset + (e.loaded || 0);
            onProgress?.(loaded, file.size);
          },
          signal,
          // Disable axios's default JSON transformer for binary bodies
          transformRequest: [(d) => d],
        });
        break;
      } catch (err) {
        if (signal?.aborted) {
          await api.delete(`/videos/upload/${uploadId}`).catch(() => {});
          throw new Error("Upload cancelled");
        }
        attempt++;
        if (attempt > retriesPerChunk) {
          // Last-ditch: read server-side status to see if the chunk
          // actually landed before we error out the whole upload.
          try {
            const st = await api.get(`/videos/upload/${uploadId}/status`);
            if (st.data?.received_size >= end) break; // chunk landed despite the error
          } catch (_e) { /* ignore */ }
          await api.delete(`/videos/upload/${uploadId}`).catch(() => {});
          throw err;
        }
        // Exponential backoff: 0.5s, 1s, 2s, …
        const delay = Math.min(8000, 500 * 2 ** (attempt - 1));
        await new Promise((r) => setTimeout(r, delay));
      }
    }

    offset = end;
    onProgress?.(offset, file.size);
  }

  // ── 3) finalise ───────────────────────────────────────────────────────────
  const { data: video } = await api.post(
    `/videos/upload/${uploadId}/finish`,
    metadata,
  );
  return video;
}
