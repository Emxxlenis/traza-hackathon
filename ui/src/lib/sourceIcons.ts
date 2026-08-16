/**
 * Icon per official source, mapped by the technical id prefix
 * (croma:<fuente>:...). Icons identify the SOURCE consulted — never the
 * entities under investigation — so no danger iconography lands on anyone.
 */

import { Building2, Database, FileText, Landmark, ShieldAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const ICON_BY_PREFIX: ReadonlyArray<readonly [string, LucideIcon]> = [
  ["croma:rues:", Building2],
  ["croma:secop:", FileText],
  ["croma:procuraduria:", ShieldAlert],
  ["croma:contraloria:", Landmark],
];

/** Maps a technical source id to its icon; unknown sources get a neutral one. */
export function sourceIcon(id: string): LucideIcon {
  for (const [prefix, icon] of ICON_BY_PREFIX) {
    if (id.startsWith(prefix)) return icon;
  }
  return Database;
}
