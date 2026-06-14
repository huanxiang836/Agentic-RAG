type SyntaxHighlighterComponent = {
  (props: Record<string, unknown>): JSX.Element | null;
  registerLanguage: (name: string, language: unknown) => void;
};

declare module "react-syntax-highlighter" {
  export const LightAsync: SyntaxHighlighterComponent;
}

declare module "react-syntax-highlighter/dist/esm/styles/hljs/atom-one-light" {
  const style: Record<string, unknown>;
  export default style;
}

declare module "react-syntax-highlighter/dist/esm/languages/hljs/bash" {
  const language: unknown;
  export default language;
}

declare module "react-syntax-highlighter/dist/esm/languages/hljs/javascript" {
  const language: unknown;
  export default language;
}

declare module "react-syntax-highlighter/dist/esm/languages/hljs/java" {
  const language: unknown;
  export default language;
}

declare module "react-syntax-highlighter/dist/esm/languages/hljs/json" {
  const language: unknown;
  export default language;
}

declare module "react-syntax-highlighter/dist/esm/languages/hljs/markdown" {
  const language: unknown;
  export default language;
}

declare module "react-syntax-highlighter/dist/esm/languages/hljs/python" {
  const language: unknown;
  export default language;
}

declare module "react-syntax-highlighter/dist/esm/languages/hljs/typescript" {
  const language: unknown;
  export default language;
}

declare module "react-syntax-highlighter/dist/esm/languages/hljs/xml" {
  const language: unknown;
  export default language;
}
