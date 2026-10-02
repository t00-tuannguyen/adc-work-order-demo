// Ước tính thời lượng — ADC-002 (T-026). Hàm thuần, test bằng node --test.

export interface Breakdown {
  setup: number;
  weight_load: number;
  volume_load: number;
  dose_load: number;
  buffer: number;
}

export interface EstimateResult {
  duration_min: number;
  breakdown: Breakdown;
  config_version: string;
}

export const SIM_LABEL = "Giá trị giả lập – không phải thông số vật lý thật";

export const BREAKDOWN_LABEL: Record<keyof Breakdown, string> = {
  setup: "Chuẩn bị",
  weight_load: "Tải trọng lượng",
  volume_load: "Tải thể tích",
  dose_load: "Tải theo liều",
  buffer: "Dự phòng",
};

/** 180 → "3h00", 45 → "0h45". */
export function formatDuration(min: number): string {
  return `${Math.floor(min / 60)}h${String(min % 60).padStart(2, "0")}`;
}

/** Các dòng breakdown theo thứ tự công thức + phần làm tròn lên bội số (để tổng khớp thời lượng). */
export function breakdownRows(e: EstimateResult): { key: string; label: string; minutes: number }[] {
  const keys = Object.keys(BREAKDOWN_LABEL) as (keyof Breakdown)[];
  const rows = keys.map((k) => ({ key: k, label: BREAKDOWN_LABEL[k], minutes: e.breakdown[k] }));
  const sum = rows.reduce((s, r) => s + r.minutes, 0);
  const rounding = Math.round((e.duration_min - sum) * 100) / 100;
  return rounding > 0 ? [...rows, { key: "rounding", label: "Làm tròn lên", minutes: rounding }] : rows;
}

/** 15.6 → "15.6′", 48 → "48′" (giữ 1 chữ số thập phân để người xem cộng lại được). */
export function formatMinutes(m: number): string {
  return `${Number.isInteger(m) ? m : (Math.round(m * 10) / 10).toString()}′`;
}
