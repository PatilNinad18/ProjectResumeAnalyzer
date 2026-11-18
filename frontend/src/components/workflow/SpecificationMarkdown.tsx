import { Children, isValidElement, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import styles from "./SpecificationMarkdown.module.css";

function containsDiffMarker(node: ReactNode): boolean {
  return Children.toArray(node).some((child) => {
    if (typeof child === "string") return child.includes("🟩");
    if (isValidElement<{ children?: ReactNode }>(child)) {
      return containsDiffMarker(child.props.children);
    }
    return false;
  });
}

interface SpecificationMarkdownProps {
  markdown: string;
}

export default function SpecificationMarkdown({ markdown }: SpecificationMarkdownProps) {
  return (
    <ReactMarkdown
      components={{
        blockquote: ({ children }) => {
          const isDiffHighlight = containsDiffMarker(children);
          return (
            <blockquote className={isDiffHighlight ? styles.diffHighlight : undefined}>
              {children}
            </blockquote>
          );
        },
      }}
    >
      {markdown || " "}
    </ReactMarkdown>
  );
}
