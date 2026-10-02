"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthFrame, Loading } from "@/components/AuthFrame";
import { getMe, logout } from "@/lib/api";
import { landingFor, type Me, ROLE_LABEL } from "@/lib/roles";

export default function PendingPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    getMe()
      .then((m) => {
        const target = landingFor(m);
        if (target !== "/pending") router.replace(target);
        else setMe(m);
      })
      .catch(() => undefined);
  }, [router]);

  if (!me) return <Loading />;

  return (
    <AuthFrame>
      <span className="badge badge-warn" style={{ alignSelf: "flex-start" }}>
        Đang chờ duyệt
      </span>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <h1>Chờ cấp quyền</h1>
        <p className="muted" style={{ margin: 0 }}>
          Yêu cầu của bạn đã gửi tới quản trị hệ thống. Bạn chưa xem được dữ liệu cho tới khi được cấp vai trò.
        </p>
      </div>
      <div className="card">
        <dl className="kv">
          <dt>Tài khoản</dt>
          <dd style={{ overflowWrap: "anywhere" }}>{me.email}</dd>
          <dt>Vai trò yêu cầu</dt>
          <dd>
            <span className="badge badge-primary">{me.requested_role ? ROLE_LABEL[me.requested_role] : "—"}</span>
          </dd>
          <dt>Trạng thái</dt>
          <dd>Chờ quản trị duyệt</dd>
        </dl>
      </div>
      <div className="notice">
        <span>
          <strong>Việc tiếp theo:</strong> khi được duyệt, đăng nhập lại (hoặc bấm “Kiểm tra lại”) để vào trang theo vai
          trò.
        </span>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn btn-primary" onClick={() => window.location.reload()}>
          Kiểm tra lại
        </button>
        <button
          className="btn btn-ghost"
          onClick={async () => {
            await logout();
            window.location.replace("/logged-out");
          }}
        >
          Đăng xuất
        </button>
      </div>
    </AuthFrame>
  );
}
