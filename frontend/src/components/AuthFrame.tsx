// Khung 2 cột cho các màn đăng nhập / đăng ký / chờ cấp quyền / đã đăng xuất (thiết kế ADC-008 màn 1–4, 6)

const LANES: { label: string; bars: [number, number, string][] }[] = [
  {
    label: "LINE A",
    bars: [
      [8, 28, "#475569"],
      [38, 22, "#C2410C"],
      [62, 24, "#475569"],
    ],
  },
  {
    label: "LINE B",
    bars: [
      [4, 20, "#C2410C"],
      [26, 30, "#A21CAF"],
      [58, 26, "#475569"],
    ],
  },
];

const FEATURES = [
  ["Tiếp nhận PDF", "AI trích xuất 8 trường, bạn xác nhận."],
  ["Xếp lịch 2 line", "Tự tìm khe sớm nhất theo ưu tiên."],
  ["Xử lý sự cố", "Phương án phục hồi trong vài giây, có duyệt."],
];

export function Brand({ dark = false }: { dark?: boolean }) {
  return (
    <div className="brand">
      <div className="brand-mark" aria-hidden="true">
        <span />
        <span />
      </div>
      <div style={{ display: "flex", flexDirection: "column" }}>
        <span style={{ fontWeight: 700, fontSize: 16, color: dark ? "#F8FAFC" : "var(--text)" }}>ADC Control Tower</span>
        <span style={{ fontSize: 12.5, color: dark ? "#94A3B8" : "var(--text-3)" }}>Điều phối lệnh chiếu xạ</span>
      </div>
    </div>
  );
}

export function AuthFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth">
      <aside className="auth-aside">
        <Brand dark />
        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          <h2>Một nơi để nhận đơn, xếp lịch và xử lý sự cố cho cả 2 line.</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }} aria-hidden="true">
            {LANES.map((lane) => (
              <div className="lane" key={lane.label}>
                <span className="lane-label">{lane.label}</span>
                <div className="lane-track">
                  {lane.bars.map(([left, width, color]) => (
                    <i key={left} style={{ left: `${left}%`, width: `${width}%`, background: color }} />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 14 }}>
            {FEATURES.map(([title, sub]) => (
              <li key={title} style={{ display: "flex", gap: 12 }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#4ADE80" strokeWidth="2.4" aria-hidden="true">
                  <path d="M5 12.5l4.5 4.5L19 7.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <span style={{ fontWeight: 600 }}>{title}</span>
                  <span className="dim" style={{ fontSize: 13.5 }}>
                    {sub}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <span style={{ fontSize: 12.5, color: "#64748B" }}>Môi trường demo · dữ liệu mô phỏng</span>
      </aside>
      <main className="auth-main">
        <div className="auth-box">{children}</div>
      </main>
    </div>
  );
}

export function Loading({ text = "Đang tải…" }: { text?: string }) {
  return (
    <div className="center-screen" role="status">
      {text}
    </div>
  );
}
