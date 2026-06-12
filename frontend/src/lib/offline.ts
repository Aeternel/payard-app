"use client";

import { openDB } from "idb";

type AttendancePayload = {
  roster_assignment: string;
  captured_at: string;
  verification_method: string;
  device_id: string;
  idempotency_key: string;
  notes?: string;
};

let databasePromise: ReturnType<typeof openDB> | null = null;

function database() {
  if (typeof indexedDB === "undefined") {
    throw new Error("Offline storage is only available in the browser.");
  }
  databasePromise ??= openDB("payyard-offline-v1", 1, {
    upgrade(db) {
      db.createObjectStore("keys");
      db.createObjectStore("attendance", { keyPath: "id" });
    },
  });
  return databasePromise;
}

async function encryptionKey(): Promise<CryptoKey> {
  const db = await database();
  const existing = await db.get("keys", "attendance-key");
  if (existing) return existing as CryptoKey;
  const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, [
    "encrypt",
    "decrypt",
  ]);
  await db.put("keys", key, "attendance-key");
  return key;
}

export async function queueAttendance(payload: AttendancePayload) {
  const key = await encryptionKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(JSON.stringify(payload));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, encoded);
  const db = await database();
  await db.put("attendance", {
    id: payload.idempotency_key,
    iv: Array.from(iv),
    ciphertext,
    expiresAt: Date.now() + 7 * 24 * 60 * 60 * 1000,
  });
}

export async function queuedAttendance(): Promise<AttendancePayload[]> {
  const db = await database();
  const key = await encryptionKey();
  const rows = await db.getAll("attendance");
  const decoded: AttendancePayload[] = [];
  for (const row of rows) {
    if (row.expiresAt < Date.now()) {
      await db.delete("attendance", row.id);
      continue;
    }
    const plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: new Uint8Array(row.iv) },
      key,
      row.ciphertext,
    );
    decoded.push(JSON.parse(new TextDecoder().decode(plaintext)));
  }
  return decoded;
}

export async function clearQueuedAttendance(ids: string[]) {
  const db = await database();
  const tx = db.transaction("attendance", "readwrite");
  await Promise.all(ids.map((id) => tx.store.delete(id)));
  await tx.done;
}
