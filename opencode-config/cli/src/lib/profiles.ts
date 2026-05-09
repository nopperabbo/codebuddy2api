import { join } from "path";
import { existsSync, readdirSync } from "fs";
import { readFile, writeFile, mkdir } from "fs/promises";
import { getConfigDir } from "./config.js";
import type { Profile, ActiveProfile } from "../types.js";

/**
 * Get the path to the profiles directory.
 */
export function getProfilesDir(): string {
  return join(getConfigDir(), "profiles");
}

/**
 * Get the path to the active-profile.json file.
 */
export function getActiveProfilePath(): string {
  return join(getConfigDir(), "active-profile.json");
}

/**
 * List all available profiles by reading the profiles directory.
 * Returns parsed Profile objects.
 */
export async function listProfiles(): Promise<Profile[]> {
  const profilesDir = getProfilesDir();

  if (!existsSync(profilesDir)) {
    return [];
  }

  const files = readdirSync(profilesDir).filter((f) => f.endsWith(".json"));
  const profiles: Profile[] = [];

  for (const file of files) {
    const content = await readFile(join(profilesDir, file), "utf-8");
    try {
      const profile = JSON.parse(content) as Profile;
      profiles.push(profile);
    } catch {
      // Skip invalid profile files
    }
  }

  return profiles;
}

/**
 * Get the currently active profile ID, or null if none set.
 */
export async function getActiveProfileId(): Promise<string | null> {
  const activePath = getActiveProfilePath();

  if (!existsSync(activePath)) {
    return null;
  }

  try {
    const content = await readFile(activePath, "utf-8");
    const data = JSON.parse(content) as ActiveProfile;
    return data.activeProfile || null;
  } catch {
    return null;
  }
}

/**
 * Set the active profile by writing active-profile.json.
 * Returns the Profile object if found, or null if the profile ID doesn't exist.
 */
export async function setActiveProfile(profileId: string): Promise<Profile | null> {
  const profiles = await listProfiles();
  const profile = profiles.find((p) => p.id === profileId);

  if (!profile) {
    return null;
  }

  const configDir = getConfigDir();
  if (!existsSync(configDir)) {
    await mkdir(configDir, { recursive: true });
  }

  const activeData: ActiveProfile = {
    activeProfile: profileId,
    switchedAt: new Date().toISOString(),
  };

  await writeFile(getActiveProfilePath(), JSON.stringify(activeData, null, 2), "utf-8");

  return profile;
}
