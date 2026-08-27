export function downloadBlob(blob: Blob, filename: string): void {
  if (typeof window === 'undefined') return
  const url = window.URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.rel = 'noopener'
    document.body.appendChild(a)
    try {
      a.click()
    } finally {
      document.body.removeChild(a)
    }
  } finally {
    window.URL.revokeObjectURL(url)
  }
}

export function suggestFilename(base: string, format: 'pdf' | 'docx' | 'md'): string {
  const safe = (base || 'report').replace(/[\\/:*?"<>|]/g, '_').trim()
  const date = new Date()
  const stamp = `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, '0')}${String(date.getDate()).padStart(2, '0')}`
  return `${safe}-${stamp}.${format}`
}
