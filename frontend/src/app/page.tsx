"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Loading } from "@/components/AuthFrame";
import { getMeOrNull } from "@/lib/api";
import { landingFor } from "@/lib/roles";

/** "Trang chính" — callback Google đưa ACTIVE về đây; chuyển tiếp theo vai trò / trạng thái. */
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    getMeOrNull()
      .then((me) => router.replace(me ? landingFor(me) : "/login"))
      .catch(() => router.replace("/login"));
  }, [router]);
  return <Loading />;
}
