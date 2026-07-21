import AddressSearch from "@/components/AddressSearch";
import AnimatedHero from "@/components/AnimatedHero";
import ResultsSection from "@/components/ResultsSection";
import HomeMapSection from "@/components/HomeMapSection";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function lookupAddress(address: string) {
  try {
    const res = await fetch(
      `${API_BASE}/governments?address=${encodeURIComponent(address)}`,
      { cache: "no-store" }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ address?: string }>;
}) {
  const params = await searchParams;
  const address = params.address;
  const data = address ? await lookupAddress(address) : null;

  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden bg-gradient-to-b from-blue-50 to-background">
        <div className="max-w-5xl mx-auto px-6 pt-16 pb-12">
          <div className="text-center mb-10">
            {!address && <AnimatedHero />}
            {address && (
              <>
                <h1 className="text-4xl font-bold mb-3">
                  Who governs your corner of Cook County?
                </h1>
                <p className="text-muted text-lg mb-8">
                  Enter any address to see every layer of local government — who
                  represents you, where the money goes, and what&apos;s on the
                  next agenda.
                </p>
              </>
            )}
            <div className="flex justify-center">
              <AddressSearch />
            </div>
          </div>
        </div>
      </section>

      {/* Results or Map */}
      <section className="max-w-5xl mx-auto px-6 pb-16">
        {address && !data && (
          <div className="text-center py-8">
            <p className="text-red-600 font-medium">
              No results found for &ldquo;{address}&rdquo;
            </p>
            <p className="text-muted text-sm mt-1">
              Check spelling and include city + IL, e.g. &ldquo;1225 Waukegan
              Rd, Glenview, IL&rdquo;
            </p>
          </div>
        )}

        {data && (
          <ResultsSection
            matchedAddress={data.matched_address}
            units={data.units}
            provenance={data.provenance}
          />
        )}

        {!address && <HomeMapSection />}
      </section>
    </div>
  );
}
