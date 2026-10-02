"use client";

import { AppShell } from "@/components/AppShell";
import { ComingSoonCard, EscalationLinkCard, IntakeLinkCard, PermissionsCard } from "@/components/cards";

export default function SalesPage() {
  return (
    <AppShell
      allow={["SALES"]}
      crumb="Tổng quan / Kinh doanh"
      title="Kinh doanh"
      subtitle="Nhận ticket của khách, báo giờ trả và xử lý đơn trễ."
    >
      {(me) => (
        <>
          <IntakeLinkCard />
          <PermissionsCard role={me.role!} />
          <ComingSoonCard title="Chờ duyệt thay đổi giờ trả" task="T-042">
            Duyệt / từ chối plan version ảnh hưởng khách (ADC-006).
          </ComingSoonCard>
          <EscalationLinkCard />
        </>
      )}
    </AppShell>
  );
}
