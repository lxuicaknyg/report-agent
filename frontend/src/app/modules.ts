import type { RouteRecordRaw } from 'vue-router'

import excelTools from '../modules/excel-tools'
import polish from '../modules/polish'
import prose from '../modules/prose'

/**
 * A tool contributed to this workspace by another team.
 *
 * Every registered module gets its own entry in the top bar and the login that
 * implies. Nothing else is shared: the report workspace's session sidebar,
 * stores and state stay behind `ReportLayout`.
 */
export interface WorkspaceModule {
  /** Stable id. Keys the top-bar entry, and prefixes the module's Pinia stores. */
  key: string
  /** Label shown in the top bar. */
  label: string
  /** Name of the route the top-bar entry opens — usually the module's landing page. */
  entry: string
  /**
   * Routes, relative to `/`. Give every one `meta: { nav: <key> }` so the top
   * bar keeps the tool's entry highlighted while any of its pages is open.
   */
  routes: RouteRecordRaw[]
}

/**
 * Registered modules, in the order they appear in the top bar.
 *
 * Adding a tool is one import and one entry — the bar and the router both read
 * this list, so nothing else in the host app changes.
 */
export const modules: WorkspaceModule[] = [prose, polish, excelTools]

export const moduleRoutes = (): RouteRecordRaw[] => modules.flatMap((item) => item.routes)

/** Top-bar entries for the registered modules, appended after the host's own. */
export const moduleNavItems = () =>
  modules.map((item) => ({ key: item.key, label: item.label, to: { name: item.entry } }))
