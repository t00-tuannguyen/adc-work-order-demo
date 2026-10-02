"use client";

import { AppShell } from "@/components/AppShell";
import { ComingSoonCard, EscalationLinkCard, PermissionsCard } from "@/components/cards";

export default function OpsPage() {
  return (
    <AppShell
      allow={["OPS_MANAGER"]}
      crumb="Tổng quan / Quản lý vận hành"
      title="Quản lý vận hành"
      subtitle="Duyệt kế hoạch, quyết định đơn bị chặn và theo dõi KPI."
    >
      {(me) => (
        <>
          <ComingSoonCard title="Plan version chờ duyệt" task="T-042">
            Duyệt / từ chối thay đổi ảnh hưởng khách; người đề xuất không tự duyệt (ADC-006).
          </ComingSoonCard>
          <ComingSoonCard title="Override đơn BLOCK" task="T-040 / T-042">
            Cho phép nhận đơn bị chặn kèm lý do (ADC-005). Đã có: kiểm tra rủi ro OK / WARN / BLOCK trên Kanban.
          </ComingSoonCard>
          <EscalationLinkCard />
          <ComingSoonCard title="Dashboard KPI · 1 line vs 2 line" task="T-046">
            On-time rate, tải line, so sánh chế độ (ADC-007).
          </ComingSoonCard>
          <PermissionsCard role={me.role!} />
        </>
      )}
    </AppShell>
  );
}
