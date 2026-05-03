# TypeScript Linting and Formatting

This project plans to use `frontend/` for a Next.js TypeScript app.

Install the frontend template first, then add or adjust the linting and formatting setup. Many template CLIs expect the target directory to be empty, and they may generate their own `package.json`, `tsconfig.json`, and ESLint config. Adding these tools after the template avoids file conflicts or overwritten config.

## Recommended Tools

- ESLint: TypeScript, React, and Next.js linting.
- Prettier: code formatting.
- TypeScript compiler: type checking with `tsc --noEmit`.
- `eslint-plugin-simple-import-sort`: import and export sorting.
- `eslint-config-prettier`: disables ESLint rules that conflict with Prettier.

## Dev Dependencies

After the Next.js app exists in `frontend/`, install the relevant dev dependencies there:

```bash
cd frontend
npm install --save-dev eslint eslint-config-next typescript prettier eslint-config-prettier eslint-plugin-simple-import-sort
```

Use the equivalent command if the project uses another package manager.

## ESLint Config

Use an explicit ESLint flat config, usually `frontend/eslint.config.mjs`:

```js
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";
import simpleImportSort from "eslint-plugin-simple-import-sort";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    plugins: {
      "simple-import-sort": simpleImportSort,
    },
    rules: {
      "simple-import-sort/imports": "warn",
      "simple-import-sort/exports": "warn",
    },
  },
  prettier,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);
```

For modern Next.js, prefer running ESLint directly instead of `next lint`.

## Prettier Config

Use `frontend/.prettierrc.json`:

```json
{
  "printWidth": 88,
  "semi": true,
  "singleQuote": false,
  "trailingComma": "all"
}
```

Use `frontend/.prettierignore` to skip generated files:

```gitignore
.next
out
build
coverage
node_modules
next-env.d.ts
```

## Package Scripts

Add scripts like these to `frontend/package.json`:

```json
{
  "scripts": {
    "lint": "eslint .",
    "lint:fix": "eslint . --fix",
    "format": "prettier . --write",
    "format:check": "prettier . --check",
    "typecheck": "tsc --noEmit"
  }
}
```

## Python Comparison

- `ruff check` is similar to `eslint .`.
- `ruff check --fix` is similar to `eslint . --fix`.
- `ruff format` is similar to `prettier . --write`.
- Python type checking with tools like mypy is similar in purpose to `tsc --noEmit`.

