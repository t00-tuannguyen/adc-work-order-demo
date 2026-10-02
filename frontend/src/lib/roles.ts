// Logic thuần (không React) — test bằng `node --test`. Nguồn: specs/user-roles.md, specs/api-contracts.md §8.

export type Role = "SALES" | "PLANNER" | "OPS_MANAGER" | "ADMIN";
export type UserStatus = "PENDING" | "ACTIVE" | "DISABLED";

export interface Me {
  id: string;
  name: string;
  email: string;
  avatar_url: string | null;
  role: Role | null;
  status: UserStatus;
  requested_role: Role | null;
}

export const ROLE_LABEL: Record<Role, string> = {
  SALES: "Kinh doanh",
  PLANNER: "Điều phối sản xuất",
  OPS_MANAGER: "Quản lý vận hành",
  ADMIN: "Quản trị hệ thống",
};

// ADMIN không tự yêu cầu được (backend trả 422)
export const REQUESTABLE_ROLES: Role[] = ["SALES", "PLANNER", "OPS_MANAGER"];

// Trang chính theo vai trò — đặc tả chưa định nghĩa, chốt tạm ở frontend (xem Nhật ký ADC-008)
export const ROLE_HOME: Record<Role, string> = {
  SALES: "/sales",
  PLANNER: "/planner",
  OPS_MANAGER: "/ops",
  ADMIN: "/admin/users",
};

/** Người dùng đã đăng nhập nên ở đâu: trang theo vai trò, hoặc màn đăng ký / chờ cấp quyền. */
export function landingFor(me: Me): string {
  if (me.status === "ACTIVE" && me.role) return ROLE_HOME[me.role];
  if (me.status === "DISABLED") return "/login?error=ACCOUNT_DISABLED";
  return me.requested_role === null ? "/signup/complete" : "/pending";
}

/** Chỉ nhận đường dẫn nội bộ — cùng luật với backend `safe_next_path`. */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return null;
  return next;
}

export function loginUrl(next?: string | null): string {
  const safe = safeNext(next);
  return safe ? `/login?next=${encodeURIComponent(safe)}` : "/login";
}

export function googleStartUrl(next?: string | null): string {
  const safe = safeNext(next);
  return safe ? `/auth/google/start?next=${encodeURIComponent(safe)}` : "/auth/google/start";
}

export interface LoginErrorInfo {
  title: string;
  detail: string;
  tone: "info" | "error";
}

export function loginErrorMessage(code: string | null | undefined): LoginErrorInfo | null {
  switch (code) {
    case null:
    case undefined:
    case "":
      return null;
    case "CANCELLED":
      return { tone: "info", title: "Bạn đã hủy đăng nhập", detail: "Bấm “Tiếp tục với Google” khi sẵn sàng." };
    case "DOMAIN_NOT_ALLOWED":
      return {
        tone: "error",
        title: "Email này không thuộc tên miền được phép",
        detail: "Hãy đăng nhập bằng tài khoản Google công ty. Nếu bạn nghĩ đây là nhầm lẫn, liên hệ quản trị hệ thống.",
      };
    case "EMAIL_NOT_VERIFIED":
      return {
        tone: "error",
        title: "Email Google chưa được xác minh",
        detail: "Xác minh email trong tài khoản Google rồi thử lại.",
      };
    case "STATE_MISMATCH":
      return {
        tone: "error",
        title: "Phiên đăng nhập đã hết hạn hoặc bị mở ở tab khác",
        detail: "Chỉ mở một tab đăng nhập và thử lại.",
      };
    case "ACCOUNT_DISABLED":
      return {
        tone: "error",
        title: "Tài khoản đã bị vô hiệu hóa",
        detail: "Liên hệ quản trị hệ thống để được mở lại.",
      };
    default:
      return {
        tone: "error",
        title: "Không đăng nhập được với Google",
        detail: "Có lỗi khi xác minh với Google. Thử lại sau ít phút.",
      };
  }
}

export type Action =
  | "UPLOAD_TICKET"
  | "VIEW_BOARD"
  | "EDIT_SCHEDULE"
  | "CHANGE_OPERATIONAL_STATE"
  | "DECLARE_INCIDENT"
  | "APPROVE_PLAN_VERSION"
  | "OVERRIDE_BLOCK"
  | "APPROVE_ESCALATION_MESSAGE"
  | "MANAGE_USERS";

// Bản sao hiển thị của specs/user-roles.md §2 — backend (src/modules/identity/permissions.py) là nơi kiểm tra thật
export const PERMISSIONS: Record<Action, { label: string; roles: Role[] }> = {
  UPLOAD_TICKET: { label: "Tải PDF / tạo work order", roles: ["SALES"] },
  VIEW_BOARD: { label: "Xem Kanban, lịch, KPI", roles: ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"] },
  EDIT_SCHEDULE: { label: "Xếp / sửa lịch", roles: ["PLANNER"] },
  CHANGE_OPERATIONAL_STATE: { label: "Chuyển trạng thái vận hành thủ công", roles: ["PLANNER"] },
  DECLARE_INCIDENT: { label: "Khai báo sự cố", roles: ["PLANNER"] },
  APPROVE_PLAN_VERSION: { label: "Duyệt / từ chối plan version", roles: ["SALES", "OPS_MANAGER"] },
  OVERRIDE_BLOCK: { label: "Override đơn BLOCK (kèm lý do)", roles: ["OPS_MANAGER"] },
  APPROVE_ESCALATION_MESSAGE: { label: "Duyệt thông điệp escalation", roles: ["SALES", "OPS_MANAGER"] },
  MANAGE_USERS: { label: "Quản lý người dùng & vai trò", roles: ["ADMIN"] },
};

export function can(role: Role | null, action: Action): boolean {
  return role !== null && PERMISSIONS[action].roles.includes(role);
}

export function initials(name: string, email: string): string {
  const words = (name || email).trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  return (words[0] ?? "?").slice(0, 2).toUpperCase();
}
