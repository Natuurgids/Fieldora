import { cpSync, copyFileSync } from "node:fs";

const output = "../../src/natureai_next/resources/excalidraw";
cpSync(
  "node_modules/@excalidraw/excalidraw/dist/prod/fonts",
  `${output}/assets/fonts`,
  { recursive: true },
);
copyFileSync("LICENSE-Excalidraw.txt", `${output}/LICENSE-Excalidraw.txt`);
copyFileSync("node_modules/react/LICENSE", `${output}/LICENSE-React.txt`);
copyFileSync("node_modules/vite/LICENSE.md", `${output}/LICENSE-Vite.txt`);
