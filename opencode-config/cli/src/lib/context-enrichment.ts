/**
 * Context Enrichment — Auto-detect project state (git, deps)
 * and format for injection into context_read responses.
 */

// ─── Types ───────────────────────────────────────────────────

export interface GitState {
  branch: string;
  uncommittedCount: number;
  lastCommitMessage: string;
  aheadOfMain: number;
}

export interface EnrichmentData {
  git: GitState | null;
  deps: string[];
  testStatus?: string;
}

// ─── Helpers ─────────────────────────────────────────────────

/**
 * Run a git command in the given directory.
 * Returns trimmed stdout on success, null on failure.
 */
async function runGit(
  args: string[],
  cwd: string,
): Promise<string | null> {
  try {
    const proc = Bun.spawn(["git", ...args], {
      cwd,
      stdout: "pipe",
      stderr: "pipe",
    });
    const text = await new Response(proc.stdout).text();
    const exitCode = await proc.exited;
    if (exitCode !== 0) return null;
    return text.trim();
  } catch {
    return null;
  }
}

// ─── getGitState ─────────────────────────────────────────────

export async function getGitState(
  projectRoot: string,
): Promise<GitState | null> {
  // Check if it's a git repo at all
  const branch = await runGit(
    ["rev-parse", "--abbrev-ref", "HEAD"],
    projectRoot,
  );
  if (branch === null) return null;

  // Uncommitted file count
  const statusOutput = await runGit(["status", "--porcelain"], projectRoot);
  const uncommittedCount =
    statusOutput !== null
      ? statusOutput
          .split("\n")
          .filter((line) => line.length > 0).length
      : 0;

  // Last commit message
  const lastCommitMessage =
    (await runGit(["log", "-1", "--format=%s"], projectRoot)) ?? "";

  // Ahead of main/master
  let aheadOfMain = 0;
  const aheadMain = await runGit(
    ["rev-list", "--count", "main..HEAD"],
    projectRoot,
  );
  if (aheadMain !== null) {
    aheadOfMain = parseInt(aheadMain, 10) || 0;
  } else {
    const aheadMaster = await runGit(
      ["rev-list", "--count", "master..HEAD"],
      projectRoot,
    );
    if (aheadMaster !== null) {
      aheadOfMain = parseInt(aheadMaster, 10) || 0;
    }
  }

  return {
    branch,
    uncommittedCount,
    lastCommitMessage,
    aheadOfMain,
  };
}

// ─── getRecentDeps ───────────────────────────────────────────

export async function getRecentDeps(
  projectRoot: string,
): Promise<string[]> {
  try {
    const pkgPath = `${projectRoot}/package.json`;
    const file = Bun.file(pkgPath);
    const exists = await file.exists();
    if (!exists) return [];

    const pkg = await file.json();
    const allDeps: Record<string, string> = {
      ...(pkg.dependencies ?? {}),
      ...(pkg.devDependencies ?? {}),
    };

    return Object.entries(allDeps)
      .slice(0, 10)
      .map(([name, version]) => {
        // Strip leading ^ ~ >= etc for cleaner display
        const clean = String(version).replace(/^[\^~>=<]+/, "");
        return `${name}@${clean}`;
      });
  } catch {
    return [];
  }
}

// ─── formatEnrichmentSection ─────────────────────────────────

export function formatEnrichmentSection(data: EnrichmentData): string {
  const lines: string[] = [];

  if (data.git) {
    lines.push(
      `- Branch: ${data.git.branch} (${data.git.aheadOfMain} ahead of main)`,
    );
    lines.push(`- Uncommitted changes: ${data.git.uncommittedCount} files`);
    lines.push(`- Last commit: ${data.git.lastCommitMessage}`);
  }

  if (data.testStatus) {
    lines.push(`- Tests: ${data.testStatus}`);
  }

  if (data.deps.length > 0) {
    lines.push(`- Dependencies: ${data.deps.join(", ")}`);
  }

  return lines.join("\n");
}

// ─── enrichContext ───────────────────────────────────────────

export async function enrichContext(projectRoot: string): Promise<string> {
  const [git, deps] = await Promise.all([
    getGitState(projectRoot),
    getRecentDeps(projectRoot),
  ]);

  return formatEnrichmentSection({ git, deps });
}
