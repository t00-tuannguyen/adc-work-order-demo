// Hàm thuần cho lỗi HTTP — tách khỏi api.ts để node --test chạy được (BUG-001).

/** Câu báo lỗi khi body không có `detail` (vd 500 text thuần). Qua HTTP/2 `statusText` luôn rỗng
 *  → không được để message rỗng, nếu không UI coi như không lỗi. */
export function fallbackMessage(status: number, statusText: string): string {
  if (statusText) return statusText;
  return status >= 500 ? `Máy chủ lỗi (HTTP ${status}). Thử lại sau.` : `Yêu cầu không hợp lệ (HTTP ${status}).`;
}
