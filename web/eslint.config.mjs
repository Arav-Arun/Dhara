import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import stylistic from "@stylistic/eslint-plugin";

// House style: Allman braces, 4-space indent, double quotes, semicolons. No Prettier.
const eslintConfig = defineConfig([
    ...nextVitals,
    ...nextTs,
    {
        plugins: { "@stylistic": stylistic },
        rules: {
            "@stylistic/brace-style": ["error", "allman", { allowSingleLine: true }],
            "@stylistic/indent": ["error", 4, { SwitchCase: 1 }],
            "@stylistic/quotes": ["error", "double", { avoidEscape: true }],
            "@stylistic/semi": ["error", "always"],
        },
    },
    globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);

export default eslintConfig;
