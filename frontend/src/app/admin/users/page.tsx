"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ApiError, type AdminUser, listUsers, patchUser } from "@/lib/api";
import { initials, type Me, ROLE_LABEL, type Role, type UserStatus } from "@/lib/roles";

const ROLES = Object.keys(ROLE_LABEL) as Role[];
const TABS: { status: UserStatus; label: string }[] = [
  { status: "PENDING", label: "Chờ duyệt" },
  { status: "ACTIVE", label: "Đang hoạt động" },
  { status: "DISABLED", label: "Vô hiệu hóa" },
];

function when(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}

function Who({ u }: { u: AdminUser }) {
  return (
    <div className="request-who">
      <span className="avatar" aria-hidden="true">
        {initials(u.name, u.email)}
      </span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600 }}>{u.name || "—"}</div>
        <div className="small muted" style={{ overflowWrap: "anywhere" }}>
          {u.email}
        </div>
      </div>
    </div>
  );
}

function PendingRow({ u, onChange }: { u: AdminUser; onChange: (id: string, p: { role?: Role; status?: UserStatus }) => void }) {
  const [role, setRole] = useState<Role>(u.requested_role ?? "SALES");
  return (
    <div className="request">
      <Who u={u} />
      <div className="request-note">
        {u.requested_role ? `Yêu cầu: ${ROLE_LABEL[u.requested_role]}` : "Chưa gửi yêu cầu vai trò"}
        {u.request_note && ` · “${u.request_note}”`}
        <div className="small" style={{ fontStyle: "normal" }}>
          Đăng ký {when(u.created_at)}
        </div>
      </div>
      <div className="request-actions">
        <label className="small muted" htmlFor={`role-${u.id}`}>
          Cấp vai trò
        </label>
        <select id={`role-${u.id}`} className="select" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
        <button className="btn btn-ghost" onClick={() => onChange(u.id, { status: "DISABLED" })}>
          Từ chối
        </button>
        <button className="btn btn-success" onClick={() => onChange(u.id, { role, status: "ACTIVE" })}>
          Cấp quyền
        </button>
      </div>
    </div>
  );
}

function UsersAdmin({ me }: { me: Me }) {
  const [tab, setTab] = useState<UserStatus>("PENDING");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const reload = useCallback(() => {
    listUsers()
      .then(setUsers)
      .catch((e) => setMessage({ tone: "error", text: e instanceof ApiError ? e.message : "Không tải được danh sách" }));
  }, []);
  useEffect(reload, [reload]);

  async function change(id: string, patch: { role?: Role; status?: UserStatus }) {
    setMessage(null);
    try {
      const u = await patchUser(id, patch);
      setMessage({ tone: "success", text: `Đã cập nhật ${u.email}: ${u.role ? ROLE_LABEL[u.role] : "—"} · ${u.status}` });
      if (u.id === me.id) window.location.reload(); // tự đổi vai trò → quyền mới có hiệu lực ngay
      reload();
    } catch (e) {
      setMessage({ tone: "error", text: e instanceof ApiError ? `${e.status}: ${e.message}` : "Không cập nhật được" });
    }
  }

  const count = (s: UserStatus) => users.filter((u) => u.status === s).length;
  const shown = users.filter((u) => u.status === tab);

  return (
    <section className="card span-all" aria-labelledby="users-title">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <h2 className="card-title" id="users-title">
          Người dùng
        </h2>
        <span className="badge">{users.length} người dùng</span>
      </div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.status}
            role="tab"
            aria-selected={tab === t.status}
            className={`tab${tab === t.status ? " active" : ""}`}
            onClick={() => setTab(t.status)}
          >
            {t.label} <span className="badge">{count(t.status)}</span>
          </button>
        ))}
      </div>
      {message && (
        <div className={`notice notice-${message.tone}`} role="status">
          {message.text}
        </div>
      )}
      {shown.length === 0 && <p className="muted" style={{ margin: 0 }}>Không có ai trong mục này.</p>}
      {tab === "PENDING" && shown.map((u) => <PendingRow key={u.id} u={u} onChange={change} />)}
      {tab !== "PENDING" && shown.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Người dùng</th>
                <th>Vai trò</th>
                <th>Đăng nhập gần nhất</th>
                <th>Trạng thái</th>
                <th aria-label="Thao tác" />
              </tr>
            </thead>
            <tbody>
              {shown.map((u) => (
                <tr key={u.id}>
                  <td>
                    <Who u={u} />
                  </td>
                  <td>
                    <label className="sr-only" htmlFor={`r-${u.id}`} style={{ position: "absolute", left: -9999 }}>
                      Vai trò của {u.email}
                    </label>
                    <select
                      id={`r-${u.id}`}
                      className="select"
                      value={u.role ?? ""}
                      onChange={(e) => change(u.id, { role: e.target.value as Role })}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABEL[r]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="small">{when(u.last_login_at)}</td>
                  <td>
                    <span className={u.status === "ACTIVE" ? "badge badge-success" : "badge badge-danger"}>
                      {u.status === "ACTIVE" ? "Hoạt động" : "Vô hiệu hóa"}
                    </span>
                    {u.id === me.id && <span className="badge" style={{ marginLeft: 6 }}>Bạn</span>}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {u.status === "ACTIVE" ? (
                      <button className="btn btn-sm btn-danger-text" onClick={() => change(u.id, { status: "DISABLED" })}>
                        Vô hiệu hóa
                      </button>
                    ) : (
                      <button
                        className="btn btn-sm"
                        disabled={!u.role}
                        onClick={() => change(u.id, { status: "ACTIVE" })}
                      >
                        Mở lại
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="notice small">
        Mọi thay đổi vai trò và trạng thái tài khoản đều ghi vào audit log. Không thể hạ quyền hoặc vô hiệu hóa quản trị
        viên cuối cùng.
      </div>
    </section>
  );
}

export default function UsersPage() {
  return (
    <AppShell
      allow={["ADMIN"]}
      crumb="Quản trị / Người dùng"
      title="Quản lý người dùng"
      subtitle="Duyệt tài khoản mới đăng ký bằng Google và cấp vai trò."
    >
      {(me) => <UsersAdmin me={me} />}
    </AppShell>
  );
}
