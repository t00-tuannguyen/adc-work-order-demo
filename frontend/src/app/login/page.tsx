"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AuthFrame } from "@/components/AuthFrame";
import { ApiError, demoLogin, getMeOrNull } from "@/lib/api";
import { googleStartUrl, landingFor, loginErrorMessage, ROLE_LABEL, type Role, safeNext } from "@/lib/roles";

const DEMO_ROLES: Role[] = ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"];

function LoginInner() {
  const params = useSearchParams();
  const router = useRouter();
  const next = safeNext(params.get("next"));
  const error = loginErrorMessage(params.get("error"));
  const [showDemo, setShowDemo] = useState(false);
  const [demoError, setDemoError] = useState<string | null>(null);

  // Đã đăng nhập rồi → không cần ở màn này
  useEffect(() => {
    if (params.get("error")) return;
    getMeOrNull()
      .then((me) => me && me.status !== "DISABLED" && router.replace(next ?? landingFor(me)))
      .catch(() => undefined);
  }, [params, next, router]);

  async function loginAsDemo(role: Role) {
    setDemoError(null);
    try {
      await demoLogin(role);
      window.location.assign(next ?? "/");
    } catch (e) {
      setDemoError(
        e instanceof ApiError && e.status === 404
          ? "Tài khoản demo chưa bật ở môi trường này (FEATURE_DEMO_LOGIN)."
          : "Không đăng nhập demo được.",
      );
    }
  }

  return (
    <AuthFrame>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <h1>Đăng nhập</h1>
        <p className="muted" style={{ margin: 0 }}>
          Dùng tài khoản Google công ty để tiếp tục.
        </p>
      </div>

      {error && (
        <div className={error.tone === "error" ? "notice notice-error" : "notice"} role="alert">
          <div>
            <strong>{error.title}</strong>
            <div>{error.detail}</div>
          </div>
        </div>
      )}
      {next && !error && (
        <div className="notice notice-warn" role="status">
          Phiên đăng nhập đã hết hạn. Đăng nhập lại để quay về trang đang làm, dữ liệu nháp vẫn được giữ.
        </div>
      )}

      {/* Nút trung tính theo thiết kế; bản chính thức phải theo hướng dẫn thương hiệu Google */}
      <a className="btn btn-block" href={googleStartUrl(next)} style={{ minHeight: 48 }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21a8 8 0 0 1 16 0" />
        </svg>
        Tiếp tục với Google
      </a>

      <div className="notice">
        <span>
          <strong>Lần đầu sử dụng?</strong> Cứ đăng nhập bằng Google, hệ thống sẽ tạo tài khoản. Quản trị cấp vai trò
          xong là bạn dùng được.
        </span>
      </div>
      <div className="small muted">Hệ thống không lưu mật khẩu. Chỉ dùng tên, email và ảnh đại diện từ Google.</div>

      <div className="divider-row">
        <span className="muted">Chính sách quyền riêng tư (chờ bổ sung)</span>
        <button
          type="button"
          className="menu-item"
          style={{ width: "auto", minHeight: 0, padding: 0, marginLeft: "auto", color: "var(--text-2)" }}
          aria-expanded={showDemo}
          onClick={() => setShowDemo((s) => !s)}
        >
          Dùng tài khoản demo
        </button>
      </div>
      {showDemo && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="small muted">Chỉ dùng khi demo / pitch. Mỗi nút đăng nhập bằng một vai trò.</div>
          <div className="role-grid">
            {DEMO_ROLES.map((role) => (
              <button key={role} type="button" className="btn btn-ghost" onClick={() => loginAsDemo(role)}>
                {ROLE_LABEL[role]}
              </button>
            ))}
          </div>
          {demoError && (
            <div className="notice notice-error" role="alert">
              {demoError}
            </div>
          )}
        </div>
      )}
    </AuthFrame>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginInner />
    </Suspense>
  );
}
