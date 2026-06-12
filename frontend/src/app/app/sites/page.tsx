"use client";

import { useEffect, useState } from "react";
import { Badge, LoadingState } from "@/components/page-state";
import { fetchAll } from "@/lib/api";

type Site = {
  id: string;
  name: string;
  client_name: string;
  address: string;
  environment: string;
  is_active: boolean;
};

export default function SitesPage() {
  const [sites, setSites] = useState<Site[] | null>(null);
  useEffect(() => {
    fetchAll<Site>("sites/?page_size=100").then(setSites);
  }, []);
  if (!sites) return <LoadingState label="Loading sites..." />;
  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Deployment map</p>
          <h1>Sites & roster</h1>
          <p>Work environments, shifts, rosters, and supervisor access.</p>
        </div>
        <button className="button">Add site</button>
      </header>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Site</th>
              <th>Client</th>
              <th>Environment</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sites.map((site) => (
              <tr key={site.id}>
                <td>
                  <strong>{site.name}</strong>
                  <br />
                  <span style={{ color: "var(--muted)" }}>{site.address}</span>
                </td>
                <td>{site.client_name || "Internal"}</td>
                <td><Badge value={site.environment} /></td>
                <td><Badge value={site.is_active ? "active" : "inactive"} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
