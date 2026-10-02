"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AuthFrame } from "@/components/AuthFrame";

function LoggedOutInner() {
  const all = useSearchParams().get("all") === "1";
  return (
    <AuthFrame>
      <span className="badge badge-success" style={{ alignSelf: "flex-start" }}>
        Đã đăng xuất
      </span>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <h1>Bạn đã đăng xuất an toàn</h1>
        <p className="muted" style={{ margin: 0 }}>
          {all
            ? "Mọi phiên trên tất cả thiết bị đã kết thúc."
            : "Phiên trên thiết bị này đã kết thúc. Tài khoản Google của bạn vẫn đăng nhập trong trình duyệt."}
        </p>
      </div>
      <a className="btn btn-primary" href="/login">
        Đăng nhập lại
      </a>
    </AuthFrame>
  );
}

export default function LoggedOutPage() {
  return (
    <Suspense>
      <LoggedOutInner />
    </Suspense>
  );
}
