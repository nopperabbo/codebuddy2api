import chalk from "chalk";
import { VERSION } from "./constants.js";

export function banner(): void {
  const title = `OpenCode JCE CLI v${VERSION}`;
  const boxWidth = Math.max(title.length + 6, 43); // min 43 inner width
  const padding = boxWidth - title.length;
  const padLeft = Math.floor(padding / 2);
  const padRight = padding - padLeft;
  const top = "╔" + "═".repeat(boxWidth) + "╗";
  const mid = "║" + " ".repeat(padLeft) + title + " ".repeat(padRight) + "║";
  const bot = "╚" + "═".repeat(boxWidth) + "╝";
  console.log(chalk.cyan(top));
  console.log(chalk.cyan(mid));
  console.log(chalk.cyan(bot));
  console.log();
}

export function info(msg: string): void {
  console.log(chalk.blue("[INFO]"), msg);
}

export function success(msg: string): void {
  console.log(chalk.green("  ✅"), msg);
}

export function warn(msg: string): void {
  console.log(chalk.yellow("  ⚠️ "), msg);
}

export function error(msg: string): void {
  console.log(chalk.red("  ❌"), msg);
}

export function skip(msg: string): void {
  console.log(chalk.yellow("[SKIP]"), msg);
}

export function heading(msg: string): void {
  console.log();
  console.log(chalk.bold.underline(msg));
}

/**
 * Format a cost value as a dollar string.
 * - Zero returns "$0.00"
 * - Sub-cent values use 4 decimal places for precision
 * - Everything else uses standard 2 decimal places
 */
export function formatCost(cost: number): string {
  if (cost === 0) return "$0.00";
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}
