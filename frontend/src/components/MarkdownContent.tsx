import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useTheme } from '@/context/ThemeContext';

type MarkdownContentProps = {
  children: string;
  className?: string;
};

/**
 * Renders markdown with GFM (tables, strikethrough, etc.) and fenced code blocks
 * highlighted via react-syntax-highlighter (theme follows app light/dark).
 */
export function MarkdownContent({ children, className }: MarkdownContentProps) {
  const { theme } = useTheme();
  const codeTheme = theme === 'dark' ? oneDark : oneLight;

  const components: Components = {
    code: ({ inline, className, children: codeChildren, ...props }: any) => {
      const match = /language-(\w+)/.exec(className || '');
      const language = match?.[1];
      const codeString = String(codeChildren).replace(/\n$/, '');

      if (inline) {
        return (
          <code
            className="rounded bg-muted px-1.5 py-0.5 text-[0.85em] font-mono break-words"
            {...props}
          >
            {codeChildren}
          </code>
        );
      }

      return (
        <SyntaxHighlighter
          language={language || 'text'}
          style={codeTheme}
          PreTag="div"
          className="rounded-md text-sm !my-3 !p-4 border border-border shadow-sm"
          showLineNumbers={codeString.split('\n').length > 4}
          wrapLines
        >
          {codeString}
        </SyntaxHighlighter>
      );
    },
  } as Components;

  return (
    <div className={className ?? 'prose dark:prose-invert prose-sm max-w-none'}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownContent;
