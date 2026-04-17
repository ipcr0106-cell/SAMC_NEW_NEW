import fs from "node:fs";
import path from "node:path";

const rootDir = process.cwd();
const inputPath = path.join(rootDir, "design-tokens", "tokens.json");
const outputPath = path.join(rootDir, "app", "tokens.generated.css");

const source = JSON.parse(fs.readFileSync(inputPath, "utf8"));

const toVarBlock = (selector, entries) => {
  const lines = Object.entries(entries).map(
    ([key, value]) => `  --ds-${key}: ${String(value)};`
  );
  return `${selector} {\n${lines.join("\n")}\n}\n`;
};

const lightTheme = source?.modes?.theme?.light ?? {};
const darkTheme = source?.modes?.theme?.dark ?? {};
const normalSize = source?.modes?.size?.normal ?? {};
const smallSize = source?.modes?.size?.small ?? {};

const mergedRoot = {
  ...normalSize,
  ...lightTheme
};

const header = [
  "/* Auto-generated file. Do not edit directly. */",
  "/* Source: design-tokens/tokens.json */",
  ""
].join("\n");

const css = [
  header,
  toVarBlock(":root", mergedRoot),
  toVarBlock(':root[data-theme="dark"]', darkTheme),
  toVarBlock(':root[data-size="small"]', smallSize)
].join("\n");

fs.writeFileSync(outputPath, css, "utf8");
console.log(`Generated: ${path.relative(rootDir, outputPath)}`);
