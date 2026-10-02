"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Brand, Loading } from "@/components/AuthFrame";
import { getMe, listEscalations, logout, logoutAll } from "@/lib/api";
import { ESCALATIONS_CHANGED } from "@/lib/risk";
import { initials, landingFor, type Me, ROLE_HOME, ROLE_LABEL, type Role } from "@/lib/roles";

interface NavItem {
  label: string;
  href?: string; // không có → chưa làm, hiện mã việc
  task?: string;
  roles: Role[];
  badge?: "escalations"; // số mục đang mở cạnh tên menu
}

// Vai trò xử lý escalation (specs/user-roles.md §2) — thấy badge đếm mục đang mở (ADC-005 T-039)
const ESCALATION_ROLES: Role[] = ["SALES", "OPS_MANAGER"];

const ALL: Role[] = ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"];

const NAV: { title: string; items: NavItem[] }[] = [
  {
    title: "Tổng quan",
    items: [
      { label: "Kinh doanh", href: ROLE_HOME.SALES, roles: ["SALES"] },
      { label: "Điều phối", href: ROLE_HOME.PLANNER, roles: ["PLANNER"] },
      { label: "Quản lý vận hành", href: ROLE_HOME.OPS_MANAGER, roles: ["OPS_MANAGER"] },
    ],
  },
  {
    title: "Vận hành",
    items: [
      { label: "Tiếp nhận đơn", href: "/intake", roles: ["SALES"] },
      { label: "Kanban lệnh", href: "/board", roles: ALL },
      { label: "Lịch Line A / B", href: "/schedule", roles: ALL },
      { label: "Sự cố line", href: "/incidents", roles: ALL },
    ],
  },
  {
    title: "Kiểm soát",
    items: [
      { label: "Chờ duyệt", href: "/approvals", roles: ALL },
      { label: "Escalation", href: "/escalations", roles: ESCALATION_ROLES, badge: "escalations" },
    ],
  },
  {
    title: "Báo cáo",
    items: [
      { label: "Dashboard KPI", task: "T-046", roles: ALL },
    ],
  },
  { title: "Quản trị", items: [{ label: "Người dùng", href: ROLE_HOME.ADMIN, roles: ["ADMIN"] }] },
];

function Avatar({ me, large = false }: { me: Me; large?: boolean }) {
  return (
    <span className={large ? "avatar avatar-lg" : "avatar"} aria-hidden="true">
      {me.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- ảnh Google, không cần tối ưu
        <img src={me.avatar_url} alt="" referrerPolicy="no-referrer" />
      ) : (
        initials(me.name, me.email)
      )}
    </span>
  );
}

function AccountMenu({ me }: { me: Me }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  async function signOut(all: boolean) {
    setBusy(true);
    await (all ? logoutAll() : logout()).catch(() => undefined);
    // replace: bấm Back không quay lại trang dữ liệu (TC7)
    window.location.replace(all ? "/logged-out?all=1" : "/logged-out");
  }

  return (
    <div className="account" ref={ref}>
      {open && (
        <div className="account-panel" role="menu" aria-label="Tài khoản">
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Avatar me={me} large />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 700 }}>{me.name || me.email}</div>
              <div className="small muted" style={{ overflowWrap: "anywhere" }}>
                {me.email}
              </div>
            </div>
          </div>
          <dl className="kv">
            <dt>Vai trò</dt>
            <dd>
              <span className="badge badge-primary">{me.role ? ROLE_LABEL[me.role] : "—"}</span>
            </dd>
            <dt>Phiên hết hạn nếu không dùng</dt>
            <dd>12 giờ</dd>
          </dl>
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: 8 }}>
            <button className="menu-item" role="menuitem" disabled={busy} onClick={() => signOut(true)}>
              Đăng xuất mọi thiết bị
            </button>
            <button className="menu-item btn-danger-text" role="menuitem" disabled={busy} onClick={() => signOut(false)}>
              Đăng xuất
            </button>
          </div>
        </div>
      )}
      <button className="account-trigger" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Avatar me={me} />
        <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <span className="account-name">{me.name || me.email}</span>
          <span className="account-role">Vai trò: {me.role ? ROLE_LABEL[me.role] : "—"}</span>
        </span>
      </button>
    </div>
  );
}

/** Tải /api/me; chưa ACTIVE → màn đăng ký/chờ; sai vai trò → thông báo 403 (API vẫn là nơi chặn thật). */
export function AppShell({
  allow,
  crumb,
  title,
  subtitle,
  children,
}: {
  allow: Role[];
  crumb: string;
  title: string;
  subtitle?: string;
  children: (me: Me) => React.ReactNode;
}) {
  const [me, setMe] = useState<Me | null>(null);
  const [openEscalations, setOpenEscalations] = useState<number | null>(null);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    getMe()
      .then((m) => (m.status === "ACTIVE" && m.role ? setMe(m) : router.replace(landingFor(m))))
      .catch(() => undefined); // 401 đã được api() chuyển sang /login?next=
  }, [router]);

  useEffect(() => {
    if (!me?.role || !ESCALATION_ROLES.includes(me.role)) return;
    const refresh = () =>
      listEscalations("open")
        .then((items) => setOpenEscalations(items.length))
        .catch(() => undefined); // badge chỉ để nhắc, lỗi thì ẩn
    void refresh();
    window.addEventListener(ESCALATIONS_CHANGED, refresh);
    return () => window.removeEventListener(ESCALATIONS_CHANGED, refresh);
  }, [me, pathname]);

  if (!me || !me.role) return <Loading />;
  const role = me.role;

  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Điều hướng chính">
        <Brand />
        {NAV.map((group) => {
          const items = group.items.filter((i) => i.roles.includes(role));
          if (!items.length) return null;
          return (
            <div className="nav-group" key={group.title}>
              <div className="nav-group-title">{group.title}</div>
              {items.map((item) =>
                item.href ? (
                  <Link
                    key={item.label}
                    href={item.href}
                    className={`nav-link${pathname === item.href ? " active" : ""}`}
                    aria-current={pathname === item.href ? "page" : undefined}
                  >
                    {item.label}
                    {item.badge === "escalations" && !!openEscalations && (
                      <span className="nav-count" aria-label={`${openEscalations} escalation đang mở`}>
                        {openEscalations}
                      </span>
                    )}
                  </Link>
                ) : (
                  <span key={item.label} className="nav-link disabled" title={`Chưa làm — ${item.task}`}>
                    {item.label}
                    <span className="soon">{item.task}</span>
                  </span>
                ),
              )}
            </div>
          );
        })}
        <div className="sidebar-foot">
          <AccountMenu me={me} />
        </div>
      </nav>
      <div className="content">
        <header className="topbar">
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div className="crumb">{crumb}</div>
            <h1>{title}</h1>
            {subtitle && <div className="muted small">{subtitle}</div>}
          </div>
          <span className="badge badge-primary">{ROLE_LABEL[role]}</span>
        </header>
        {allow.includes(role) ? (
          <div className="page">{children(me)}</div>
        ) : (
          <div className="page">
            <div className="card">
              <div className="card-title">Bạn không có quyền xem trang này</div>
              <p className="muted" style={{ margin: 0 }}>
                Trang dành cho {allow.map((r) => ROLE_LABEL[r]).join(", ")}.
              </p>
              <Link className="btn" href={ROLE_HOME[role]} style={{ alignSelf: "flex-start" }}>
                Về trang của tôi
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
