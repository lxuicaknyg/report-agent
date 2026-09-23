import { hostApi } from './client'
import type { ApiResult, ParsedTable } from '../../types'

export const supplementApi = {
  /** Read pasted text back as the table it would become.
   *
   * Parsing lives on the server so the preview the user approves and the rows
   * that reach the report are the same read of the same text. Text that is not
   * a table comes back as an error whose message is written for the person who
   * pasted it.
   */
  previewTable(text: string): Promise<ApiResult<ParsedTable>> {
    return hostApi.post<ParsedTable>('/supplements/preview', { text })
  },
}
