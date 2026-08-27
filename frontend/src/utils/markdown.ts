import { marked, Renderer, type MarkedExtension } from 'marked'

const ESCAPE_MAP: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (ch) => ESCAPE_MAP[ch] ?? ch)
}

class MdRenderer extends Renderer {
  heading({ tokens, depth }: { tokens: unknown[]; depth: number }): string {
    const text = this.parser.parseInline(tokens as Parameters<typeof this.parser.parseInline>[0])
    return `<h${depth} class="md-h md-h${depth}">${text}</h${depth}>`
  }

  paragraph({ tokens }: { tokens: unknown[] }): string {
    const text = this.parser.parseInline(tokens as Parameters<typeof this.parser.parseInline>[0])
    return `<p class="md-p">${text}</p>`
  }

  list(token: unknown): string {
    const t = token as { ordered: boolean; start?: number | ''; items: Array<{ tokens: unknown[] }> }
    const tag = t.ordered ? 'ol' : 'ul'
    const cls = t.ordered ? 'md-ol' : 'md-ul'
    const startAttr = t.ordered && typeof t.start === 'number' && t.start !== 1 ? ` start="${t.start}"` : ''
    const body = t.items
      .map((item) => {
        const inner = (item.tokens as unknown[])
          .map((tt) => {
            const u = tt as { type: string; tokens?: unknown[]; raw?: string; text?: string }
            if (u.type === 'list') return this.list(u)
            if (u.type === 'paragraph' || (u.tokens && Array.isArray(u.tokens))) {
              return this.parser.parseInline(u.tokens as Parameters<typeof this.parser.parseInline>[0])
            }
            if (u.type === 'text') {
              if (u.tokens && Array.isArray(u.tokens)) {
                return this.parser.parseInline(u.tokens as Parameters<typeof this.parser.parseInline>[0])
              }
              return escapeHtml(String(u.text ?? u.raw ?? ''))
            }
            return ''
          })
          .filter(Boolean)
          .join('')
        return `<li class="md-li">${inner}</li>`
      })
      .join('')
    return `<${tag}${startAttr} class="${cls}">${body}</${tag}>`
  }

  listitem(): string {
    return ''
  }

  strong({ tokens }: { tokens: unknown[] }): string {
    const text = this.parser.parseInline(tokens as Parameters<typeof this.parser.parseInline>[0])
    return `<strong class="md-strong">${text}</strong>`
  }

  em({ tokens }: { tokens: unknown[] }): string {
    const text = this.parser.parseInline(tokens as Parameters<typeof this.parser.parseInline>[0])
    return `<em class="md-em">${text}</em>`
  }

  codespan({ text }: { text: string }): string {
    return `<code class="md-inline-code">${escapeHtml(text)}</code>`
  }

  link(linkToken: unknown): string {
    const l = linkToken as { href: string; title?: string | null; tokens: unknown[] }
    const text = this.parser.parseInline(l.tokens as Parameters<typeof this.parser.parseInline>[0])
    const t = l.title ? ` title="${escapeHtml(l.title)}"` : ''
    return `<a class="md-link" href="${escapeHtml(l.href)}"${t} target="_blank" rel="noopener noreferrer">${text}</a>`
  }

  html(): string {
    return ''
  }

  text(token: { text?: string; raw?: string }): string {
    return escapeHtml(String(token.text ?? token.raw ?? ''))
  }
}

marked.setOptions({
  gfm: true,
  breaks: true,
})

marked.use({ renderer: new MdRenderer() } as MarkedExtension)

export function renderMarkdown(src: string | null | undefined): string {
  if (!src) return ''
  try {
    return String(marked.parse(src) ?? '')
  } catch {
    return ''
  }
}
