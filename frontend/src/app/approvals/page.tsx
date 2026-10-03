"use client";

// Chờ duyệt — ADC-006 §UI/UX (T-042). Mỗi plan version chờ duyệt một thẻ: nguồn (sự cố / đơn mới / xếp tay), số đơn
// bị ảnh hưởng, danh sách thay đổi có nhãn loại, lịch trước → sau, lý do (giải thích của Scheduler); Duyệt / Từ chối.
// Duyệt cả version (FR 12); từ chối bắt buộc lý do → đơn liên quan "Cần xếp lại". Chỉ Kinh doanh / Quản lý vận hành.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { type Notice, PlanVersionCard } from "@/components/PlanVersionCard";
import { getPlanDiff, listPendingPlanVersions } from "@/lib/api";
import type { PlanDiff } from "@/lib/approval";
import type { Role } from "@/lib/roles";

const ALL: Role[] = ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"];

async function fetchPending(): Promise<PlanDiff[]> {
  const versions = await listPendingPlanVersions();
  return Promise.all(versions.map((v) => getPlanDiff(v.id)));
}

function Pending({ role }: { role: Role }) {
  const [diffs, setDiffs] = useState<PlanDiff[] | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const load = useCallback(
    () =>
      fetchPending()
        .then(setDiffs)
        .catch(() => setNotice({ tone: "error", text: "Không tải được danh sách chờ duyệt." })),
    [],
  );

  useEffect(() => {
    fetchPending()
      .then(setDiffs)
      .catch(() => setNotice({ tone: "error", text: "Không tải được danh sách chờ duyệt." }));
  }, []);

  async function decided(n: Notice) {
    setNotice(n);
    await load();
  }

  return (
    <>
      {notice && (
        <div className={`notice notice-${notice.tone} span-all`} role="status">
          {notice.text}
        </div>
      )}
      {!diffs ? (
        <p className="muted span-all">Đang tải…</p>
      ) : diffs.length === 0 ? (
        <section className="card span-all">
          <p className="muted" style={{ margin: 0 }}>
            Không có plan version nào chờ duyệt. Lịch đang áp dụng xem ở <Link href="/schedule">Lịch Line A / B</Link>.
          </p>
        </section>
      ) : (
        diffs.map((d) => (
          <PlanVersionCard
            key={d.plan_version.id}
            diff={d}
            role={role}
            onDecided={decided}
            compareHref={`/approvals/${d.plan_version.id}`}
          />
        ))
      )}
      <p className="small muted span-all">
        Thay đổi ảnh hưởng khách (đổi giờ trả, hoãn do sự cố, đổi ưu tiên, nhận đơn khi cảnh báo) chỉ áp dụng sau khi
        người duyệt bấm duyệt. AI không có quyền duyệt.
      </p>
    </>
  );
}

export default function ApprovalsPage() {
  return (
    <AppShell
      allow={ALL}
      crumb="Kiểm soát / Chờ duyệt"
      title="Chờ duyệt"
      subtitle="Phương án lịch cần người duyệt trước khi áp dụng — duyệt hoặc từ chối cả version."
    >
      {(me) => <Pending role={me.role!} />}
    </AppShell>
  );
}
