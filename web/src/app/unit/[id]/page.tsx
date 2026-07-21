import Link from "next/link";
import UnitDetail from "@/components/UnitDetail";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchJSON(path: string) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function UnitPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [unit, officialsData, financesData] = await Promise.all([
    fetchJSON(`/units/${id}`),
    fetchJSON(`/units/${id}/officials`),
    fetchJSON(`/units/${id}/finances?years_back=3`),
  ]);

  if (!unit) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-12 text-center">
        <h1 className="text-2xl font-bold mb-2">Unit not found</h1>
        <p className="text-muted">
          No government unit with ID &ldquo;{id}&rdquo;.
        </p>
        <Link href="/" className="text-accent underline mt-4 inline-block">
          Back to search
        </Link>
      </div>
    );
  }

  return (
    <UnitDetail
      unit={unit}
      officials={officialsData?.officials || []}
      officialsProvenance={officialsData?.provenance}
      years={financesData?.years || []}
      financesProvenance={financesData?.provenance}
    />
  );
}
