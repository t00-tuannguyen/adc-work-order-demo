"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthFrame, Loading } from "@/components/AuthFrame";
import { ApiError, completeSignup, getMe, logout } from "@/lib/api";
import { initials, landingFor, type Me, REQUESTABLE_ROLES, ROLE_LABEL, type Role } from "@/lib/roles";

const ROLE_HINT: Record<Role, string> = {
  SALES: "Tải PDF ticket, duyệt thay đổi giờ trả, xử lý escalation với khách.",
  PLANNER: "Xếp / sửa lịch 2 line, khai báo sự cố.",
  OPS_MANAGER: "Duyệt plan version, override đơn bị chặn.",
  ADMIN: "",
};

export default function SignupCompletePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [role, setRole] = useState<Role>("SALES");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getMe()
      .then((m) => {
        const target = landingFor(m);
        if (target !== "/signup/complete") router.replace(target);
        else setMe(m);
      })
      .catch(() => undefined);
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await completeSignup(role, note);
      router.replace("/pending");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không gửi được yêu cầu");
      setBusy(false);
    }
  }

  if (!me) return <Loading />;

  return (
    <AuthFrame>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <h1>Hoàn tất đăng ký</h1>
        <p className="muted" style={{ margin: 0 }}>
          Chọn vai trò bạn cần. Quản trị hệ thống sẽ duyệt trước khi bạn dùng được dữ liệu.
        </p>
      </div>
      <div className="card" style={{ flexDirection: "row", alignItems: "center", padding: 14 }}>
        <span className="avatar avatar-lg" aria-hidden="true">
          {initials(me.name, me.email)}
        </span>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700 }}>{me.name || "—"}</div>
          <div className="small muted" style={{ overflowWrap: "anywhere" }}>
            {me.email}
          </div>
          <div className="small muted">Lấy từ tài khoản Google</div>
        </div>
      </div>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <fieldset style={{ border: 0, margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          <legend className="small" style={{ fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>
            Vai trò yêu cầu
          </legend>
          {REQUESTABLE_ROLES.map((r) => (
            <label
              key={r}
              className="card"
              style={{
                flexDirection: "row",
                gap: 12,
                padding: 12,
                cursor: "pointer",
                borderColor: role === r ? "var(--primary)" : undefined,
              }}
            >
              <input type="radio" name="role" value={r} checked={role === r} onChange={() => setRole(r)} />
              <span>
                <span style={{ fontWeight: 600 }}>{ROLE_LABEL[r]}</span>
                <span className="small muted" style={{ display: "block" }}>
                  {ROLE_HINT[r]}
                </span>
              </span>
            </label>
          ))}
        </fieldset>
        <div className="field">
          <label htmlFor="note">Ghi chú cho quản trị (không bắt buộc)</label>
          <textarea
            id="note"
            className="textarea"
            maxLength={500}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Ví dụ: trưởng ca sáng, phụ trách Line A"
          />
        </div>
        {error && (
          <div className="notice notice-error" role="alert">
            {error}
          </div>
        )}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy ? "Đang gửi…" : "Gửi yêu cầu"}
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={async () => {
            await logout();
            window.location.replace("/logged-out");
          }}
        >
          Đăng xuất
        </button>
      </form>
    </AuthFrame>
  );
}
