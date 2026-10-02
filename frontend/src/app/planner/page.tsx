"use client";

import { AppShell } from "@/components/AppShell";
import { PermissionsCard, ScheduleLinkCard } from "@/components/cards";
import { IncidentCard } from "@/components/IncidentForm";

export default function PlannerPage() {
  return (
    <AppShell
      allow={["PLANNER"]}
      crumb="Tổng quan / Điều phối"
      title="Điều phối sản xuất"
      subtitle="Xếp lịch Line A / B và xử lý sự cố. Lịch tự tính theo luật; AI chỉ giải thích."
    >
      {(me) => (
        <>
          <ScheduleLinkCard />
          <IncidentCard />
          <PermissionsCard role={me.role!} />
        </>
      )}
    </AppShell>
  );
}
