// Status page — Phase 1 D-12 minimal health/status readout.
// Server Component: the fetch to the backend resolves before the response is
// sent to the browser, so there is no client-visible loading spinner by design.

type Taxonomy = {
  ticker: string;
  name: string;
  sub_sector: string;
};

type Company = {
  taxonomy: Taxonomy;
};

type PageState =
  | { kind: "error" }
  | { kind: "empty" }
  | { kind: "healthy"; count: number };

async function fetchCompanies(): Promise<PageState> {
  const backendUrl = process.env.BACKEND_URL ?? "http://backend:8000";

  try {
    const response = await fetch(`${backendUrl}/companies`, {
      cache: "no-store",
      // UI-SPEC "loading" row: an unresponsive backend must fall through to
      // the error state rather than hanging the page render indefinitely.
      signal: AbortSignal.timeout(5000),
    });

    if (!response.ok) {
      return { kind: "error" };
    }

    const companies = (await response.json()) as Company[];

    if (!Array.isArray(companies) || companies.length === 0) {
      return { kind: "empty" };
    }

    return { kind: "healthy", count: companies.length };
  } catch {
    return { kind: "error" };
  }
}

export default async function StatusPage() {
  const state = await fetchCompanies();
  const timestamp = new Date().toISOString();

  return (
    <div
      style={{
        background: "#FFFFFF",
        minHeight: "100vh",
        paddingTop: 64,
        paddingBottom: 64,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div style={{ width: "100%", maxWidth: 480, padding: "0 16px" }}>
        <h1
          style={{
            fontSize: 24,
            fontWeight: 600,
            lineHeight: 1.2,
            marginBottom: 32,
            color: "#171717",
          }}
        >
          Data Center Stocks
        </h1>

        <div
          style={{
            background: "#F4F5F7",
            padding: 24,
            borderRadius: 8,
          }}
        >
          {state.kind === "error" && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span
                  aria-hidden
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: "#DC2626",
                    display: "inline-block",
                  }}
                />
                <span style={{ fontSize: 16, fontWeight: 400, color: "#DC2626" }}>
                  API unreachable
                </span>
              </div>
              <p style={{ fontSize: 14, fontWeight: 400, marginTop: 8, color: "#171717" }}>
                Could not reach the backend. Confirm the backend service is running, then
                refresh this page.
              </p>
            </>
          )}

          {state.kind === "empty" && (
            <>
              <p style={{ fontSize: 16, fontWeight: 400, color: "#171717" }}>
                No companies tracked yet
              </p>
              <p style={{ fontSize: 14, fontWeight: 400, marginTop: 8, color: "#171717" }}>
                sectors.yaml has no tickers, or ingestion hasn&apos;t run yet. Check the
                taxonomy config and run the refresh script.
              </p>
            </>
          )}

          {state.kind === "healthy" && (
            <>
              <div style={{ fontSize: 32, fontWeight: 600, lineHeight: 1.2, color: "#171717" }}>
                {`${state.count} ${state.count === 1 ? "company tracked" : "companies tracked"}`}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 8 }}>
                <span
                  aria-hidden
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: "#16A34A",
                    display: "inline-block",
                  }}
                />
                <span style={{ fontSize: 16, fontWeight: 400, color: "#16A34A" }}>
                  API: healthy
                </span>
                <span style={{ fontSize: 14, fontWeight: 400, color: "#171717" }}>
                  · as of {timestamp}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
