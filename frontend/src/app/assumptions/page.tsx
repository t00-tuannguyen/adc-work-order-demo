"use client";

// Reset dữ liệu demo — ADC-002 (T-026). Không còn trong menu (ẩn giả định vận hành, 02/10/2026); vào thẳng URL khi demo.
import { AppShell } from "@/components/AppShell";
import { DemoResetCard } from "@/components/cards";

export default function AssumptionsPage() {
  return (
    <AppShell
      allow={["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"]}
      crumb="Demo / Reset dữ liệu"
      title="Reset dữ liệu demo"
      subtitle="Xóa lịch, sự cố, dữ liệu tiếp nhận và nạp lại đơn mẫu."
    >
      {() => <DemoResetCard />}
    </AppShell>
  );
}
