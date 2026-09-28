import { NextResponse } from "next/server";

const SYNTHETIC_TARGET = "50000000-0000-0000-0000-000000000002";

export async function POST() {
  const apiBase = process.env.API_BASE_URL ?? "http://localhost:8000";
  const response = await fetch(`${apiBase}/v1/assessments`, {
    method: "POST",
    headers: {
      authorization: "Bearer student-a1",
      "content-type": "application/json",
    },
    body: JSON.stringify({ course_id: SYNTHETIC_TARGET }),
    cache: "no-store",
  });
  const body: unknown = await response.json();
  return NextResponse.json(body, { status: response.status });
}

